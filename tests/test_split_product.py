import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from backend.split_product import solid_plate, candidate_alpha, mask_contract, validate_mask, paint_constraints, foreground_plate, product_quality
from backend.split_product import (alpha_boundary, build_trimap, edge_contamination,
                                   interior_holes, refine_alpha, three_background_check)


def _aa_fixture(size=(60, 60), bg=(255, 255, 255), subject=(20, 40, 80)):
    """白底 + 深色主体，主体外圈 1 像素是 50% 抗锯齿（RGB 是主体与旧底色的混合）。

    这是**诚实的抗锯齿**：不是污染，而是真正的半透明边缘。
    """
    img = Image.new("RGBA", size, bg + (255,))
    d = ImageDraw.Draw(img)
    mix = tuple((subject[i] + bg[i]) // 2 for i in range(3))
    d.rectangle((20, 20, 40, 40), fill=mix + (255,))
    d.rectangle((21, 21, 39, 39), fill=subject + (255,))
    alpha = Image.new("L", size, 0)
    ImageDraw.Draw(alpha).rectangle((20, 20, 40, 40), fill=128)
    ImageDraw.Draw(alpha).rectangle((21, 21, 39, 39), fill=255)
    plate = img.copy()
    plate.putalpha(alpha)
    return img, alpha, plate, subject, bg


def _contaminated_fixture(size=(60, 60), bg=(255, 255, 255), subject=(20, 40, 80)):
    """抠图把主体外圈 **2 像素的纯背景**也吃进来了 —— 方案 §4.3 的「白边」。

    与 `_aa_fixture` 的区别：这里边缘 RGB 就是旧底色本身，不是混合。
    """
    img = Image.new("RGBA", size, bg + (255,))
    ImageDraw.Draw(img).rectangle((22, 22, 38, 38), fill=subject + (255,))
    alpha = Image.new("L", size, 0)
    ImageDraw.Draw(alpha).rectangle((20, 20, 40, 40), fill=128)      # 2px 纯背景环
    ImageDraw.Draw(alpha).rectangle((22, 22, 38, 38), fill=255)
    plate = img.copy()
    plate.putalpha(alpha)
    return img, alpha, plate, subject, bg


class CutoutQualityTests(unittest.TestCase):
    def test_trimap_splits_three_states(self):
        alpha = Image.new("L", (10, 1))
        for x, v in enumerate((0, 4, 8, 128, 200, 249, 250, 255)):
            alpha.putpixel((x, 0), v)
        tri = build_trimap(alpha)
        self.assertEqual([tri.getpixel((x, 0)) for x in range(8)],
                         [0, 0, 0, 128, 128, 128, 255, 255])

    def test_refine_removes_white_edge_and_recovers_subject_color(self):
        # ① 诚实抗锯齿（50% 混合）：matting 必须把 alpha 估回 ~50% 且 RGB 还原成主体本色
        img, alpha, plate, subject, bg = _aa_fixture()
        soft, refined, stats = refine_alpha(img, alpha, bg)
        self.assertGreater(stats["refined"], 0, stats)
        px = refined.getpixel((20, 30))
        self.assertLess(max(abs(px[i] - subject[i]) for i in range(3)), 6, px)
        self.assertAlmostEqual(soft.getpixel((20, 30)), 128, delta=12)
        # 确定前景 / 确定背景的像素一律不动
        self.assertEqual(refined.getpixel((30, 30))[:3], subject)
        self.assertEqual(soft.getpixel((0, 0)), 0)
        self.assertEqual(soft.getpixel((30, 30)), 255)
        # ② 真污染（边缘就是旧底色）：去污染后环带不应再接近旧背景色
        img2, alpha2, plate2, _, bg2 = _contaminated_fixture()
        before = edge_contamination(plate2, alpha_boundary(alpha2)[0], bg2)
        self.assertGreater(before["ratio"], 0.5, before)
        soft2, refined2, _ = refine_alpha(img2, alpha2, bg2)
        after = edge_contamination(refined2, alpha_boundary(soft2)[0], bg2)
        self.assertLess(after["ratio"], 0.2, after)

    def test_three_background_check_flags_halo_then_passes_after_refine(self):
        img, alpha, plate, subject, bg = _contaminated_fixture()
        bad = three_background_check(plate, alpha, bg)
        self.assertFalse(bad["checks"]["dark"], bad["checks"])
        self.assertTrue(any(i["kind"] == "edge_halo" for i in bad["issues"]), bad["issues"])
        soft, refined, _ = refine_alpha(img, alpha, bg)
        good = three_background_check(refined, soft, bg)
        for key in ("white", "dark", "checker", "structure"):
            self.assertTrue(good["checks"][key], (key, good))
        self.assertEqual(good["issues"], [], good["issues"])

    def test_honest_antialiasing_passes_without_refine(self):
        """诚实的抗锯齿边缘不该被误判成色边 / 污染（否则门禁会永远拦住正常结果）。"""
        img, alpha, plate, subject, bg = _aa_fixture()
        res = three_background_check(plate, alpha, bg)
        self.assertTrue(res["checks"]["white"], res["metrics"])
        self.assertTrue(res["checks"]["dark"], res["metrics"])
        self.assertTrue(res["checks"]["structure"], res["metrics"])
        self.assertFalse(any(i["kind"] == "edge_contamination" for i in res["issues"]), res["issues"])

    def test_square_subject_is_not_mistaken_for_rect_residue(self):
        """正方形主体的 alpha 填充率本来就是 1.0 —— 不能因此报「矩形残留」。"""
        img = Image.new("RGBA", (60, 60), (255, 255, 255, 255))
        ImageDraw.Draw(img).rectangle((20, 20, 40, 40), fill=(20, 40, 80, 255))
        alpha = Image.new("L", (60, 60), 0)
        ImageDraw.Draw(alpha).rectangle((20, 20, 40, 40), fill=255)
        plate = img.copy(); plate.putalpha(alpha)
        res = three_background_check(plate, alpha, (255, 255, 255))
        self.assertFalse(any(i["kind"] == "rect_residue" for i in res["issues"]), res["issues"])
        self.assertTrue(res["checks"]["structure"], res["metrics"])

    def test_rectangle_and_full_canvas_are_blocked(self):
        img = Image.new("RGBA", (50, 50), (255, 255, 255, 255))
        rect = Image.new("L", (50, 50), 0)
        ImageDraw.Draw(rect).rectangle((10, 10, 39, 39), fill=255)
        plate = img.copy(); plate.putalpha(rect)
        res = three_background_check(plate, rect, (255, 255, 255))
        self.assertFalse(res["checks"]["structure"], res["checks"])
        self.assertTrue(any(i["kind"] == "rect_residue" for i in res["issues"]), res["issues"])
        full = Image.new("L", (50, 50), 255)
        res2 = three_background_check(img, full, (255, 255, 255))
        self.assertTrue(any(i["kind"] == "full_canvas" for i in res2["issues"]), res2["issues"])
        empty = Image.new("L", (50, 50), 0)
        res3 = three_background_check(img, empty, (255, 255, 255))
        self.assertTrue(any(i["kind"] == "subject_missing" for i in res3["issues"]), res3["issues"])

    def test_interior_holes_counts_only_disconnected_transparency(self):
        alpha = Image.new("L", (40, 40), 0)
        d = ImageDraw.Draw(alpha)
        d.rectangle((5, 5, 34, 34), fill=255)
        d.rectangle((15, 15, 24, 24), fill=0)          # 真正的内部孔洞
        self.assertEqual(interior_holes(alpha.point(lambda v: 255 if v >= 128 else 0)), 100)
        ring = Image.new("L", (40, 40), 0)
        ImageDraw.Draw(ring).ellipse((5, 5, 34, 34), fill=255)
        ImageDraw.Draw(ring).ellipse((12, 12, 27, 27), fill=0)
        # 环形主体的内圈与外界不连通 → 算孔洞，但不应达到「异常」阈值
        holes = interior_holes(ring.point(lambda v: 255 if v >= 128 else 0))
        opaque = ring.point(lambda v: 255 if v >= 128 else 0).histogram()[255]
        self.assertGreater(holes, 0)
        self.assertLessEqual(holes, max(64, int(opaque * 0.6)))

    def test_quality_passed_needs_both_objective_and_confirmation(self):
        img, alpha, plate, subject, bg = _contaminated_fixture()
        soft, refined, _ = refine_alpha(img, alpha, bg)
        contract = mask_contract(soft, 1)
        obj = three_background_check(refined, soft, bg)
        # 只有用户确认 → 仍不通过（客观检查必须也过；这里先给「不过」的客观结论）
        bad_obj = {"checks": {"white": False, "dark": False, "checker": False, "structure": False},
                   "issues": [], "metrics": {}}
        allok = dict.fromkeys(("white", "dark", "checker", "structure"), True)
        self.assertNotEqual(
            product_quality(soft, img.size, contract, allok, bad_obj)["status"], "quality_passed")
        # 客观通过但没有用户确认 → 仍不通过（§7「任务结束不等于质量通过」）
        q = product_quality(soft, img.size, contract, {}, obj)
        self.assertNotEqual(q["status"], "quality_passed")
        self.assertTrue(any(i["kind"] == "product_review" for i in q["issues"]), q["issues"])
        # 两者都满足 → 通过
        q2 = product_quality(soft, img.size, contract, allok, obj)
        self.assertEqual(q2["status"], "quality_passed")
        self.assertEqual(q2["maskRevision"], 1)
        self.assertEqual(q2["objective"], obj["checks"])

class ProductTests(unittest.TestCase):
    def fixture(self):
        image=Image.new('RGBA',(60,40),'white')
        draw=ImageDraw.Draw(image)
        draw.rectangle((15,8,30,30), fill=(40,80,120,255))
        draw.line((32,10,50,11),fill=(15,25,35,255),width=1)
        draw.point((3,3),fill='black')
        return image

    def test_exact_color_and_no_generation(self):
        for color,rgb in (('#ffffff',(255,255,255)),('#e8dfca',(232,223,202))):
            p=solid_plate((64,48),color)
            self.assertEqual(p.getextrema(),tuple((c,c) for c in rgb)+( (255,255),))

    def test_candidate_preserves_small_parts_and_core_without_morphology(self):
        src=self.fixture();alpha,info=candidate_alpha(src)
        self.assertEqual(alpha.getpixel((3,3)),255)
        self.assertEqual(alpha.getpixel((45,11)),255)
        plate=foreground_plate(src,alpha,info['background'])
        self.assertEqual(plate.getpixel((20,20)),src.getpixel((20,20)))
        self.assertEqual(alpha.getpixel((0,0)),0)
        self.assertEqual(product_quality(alpha,src.size,mask_contract(alpha,1))['status'],'needs_local_correction')

    def test_invalid_contract_and_degenerate_masks_block(self):
        src=self.fixture();alpha,_=candidate_alpha(src);contract=mask_contract(alpha,1)
        self.assertIn('mask_empty',validate_mask(Image.new('L',src.size),src.size))
        self.assertIn('mask_full',validate_mask(Image.new('L',src.size,255),src.size))
        self.assertIn('mask_dimensions',validate_mask(Image.new('L',(59,40)),src.size))
        self.assertIn('mask_origin',validate_mask(alpha,src.size,{**contract,'origin':[1,0]}))
        self.assertIn('mask_polarity',validate_mask(alpha,src.size,{**contract,'polarity':'black_foreground'}))

    def test_brush_order_and_structural_holes_preserved(self):
        base=Image.new('L',(40,40),255)
        hints={'strokes':[{'mode':'exclude','points':[[20,20,5]]},{'mode':'include','points':[[20,20,1]]}]}
        mask=paint_constraints(base,hints)
        self.assertEqual(mask.getpixel((20,20)),255)
        self.assertEqual(mask.getpixel((23,20)),0)
        self.assertEqual(mask.getpixel((1,1)),255)
        with self.assertRaises(ValueError):paint_constraints(base,{'include':[[float('nan'),0,2]]})

    def test_unmix_edges_without_changing_core(self):
        src=Image.new('RGBA',(3,1),(120,120,120,255));src.putpixel((0,0),(128,128,128,255))
        alpha=Image.new('L',src.size,255);alpha.putpixel((0,0),127)
        plate=foreground_plate(src,alpha,[255,255,255])
        self.assertLessEqual(plate.getpixel((0,0))[0],1)
        self.assertEqual(plate.getpixel((1,0)),src.getpixel((1,0)))

    def test_confirmation_belongs_to_current_valid_candidate(self):
        src=self.fixture();mask,_=candidate_alpha(src);c=mask_contract(mask,7)
        allok=dict.fromkeys(('white','dark','checker','structure'),True)
        obj={'checks':dict(allok),'issues':[],'metrics':{}}
        q=product_quality(mask,src.size,c,allok,obj)
        self.assertEqual(q['status'],'quality_passed')
        self.assertEqual(q['maskRevision'],7)
        self.assertNotEqual(product_quality(Image.new('L',src.size),src.size,c,q['checks'],obj)['status'],'quality_passed')
