"""竖屏一级页面（手机形态）的静态约定。

老板 2026-11-13：检测到页面画幅比例变成竖屏时，把侧边栏换成一级页面；一级页面改成「我的」
（资料卡 + 设置列表 + 底部标签栏）。
这里只钉最容易在后续改动中被悄悄弄坏的几处，不测视觉。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_index_shell():
    html = read('static/index.html')

    # 一级页面 + 底部标签栏标记
    assert 'id="mobileHome"' in html
    assert 'id="mobileTabs"' in html
    for tab in ('home', 'xvai', 'online', 'asset-manager'):
        assert f'data-tab="{tab}"' in html

    # 竖屏才显示：靠 body 上的 mobile-portrait / mhome-on 两个类
    assert "document.body.classList.toggle('mobile-portrait'" in html
    assert "document.body.classList.add('mhome-on')" in html
    assert "document.body.classList.remove('mhome-on')" in html
    # 切到具体页面要收起一级页面（否则 iframe 被透明层盖住点不动）
    assert 'document.body.classList.remove(\'mhome-on\');\n            mobileSetTabActive(id);' in html

    # 关键样式：隐藏侧边栏 / 舞台让出标签栏高度 / 取消整页缩放 / 隐藏悬浮胶囊
    assert 'body.mobile-portrait .sidebar { display: none !important; }' in html
    assert 'height: calc(100vh - 62px - env(safe-area-inset-bottom, 0px));' in html
    assert 'html.studio-ui-scaled body.mobile-portrait {' in html
    assert 'body.mobile-portrait ~ #xvai-entry { display: none !important; }' in html

    # 恢复当前页之后必须再算一次竖屏状态（switchUI 会摘掉 mhome-on）
    tail = html.split('function restoreActivePage()', 1)[1].split('document.addEventListener', 1)[0]
    assert tail.index('switchUI(trigger, id') < tail.rindex('syncPortraitNav();')

    # 竖屏那三个页面 = 标签栏那三个
    assert "const MOBILE_TAB_PAGES = ['xvai', 'online', 'asset-manager'];" in html


def test_me_page():
    """一级页面 = 我的：资料卡 + 设置行（老板 2026-11-13 第二次改）。"""
    html = read('static/index.html')

    # 三张功能卡已撤掉，换成资料卡 + 两个分组
    assert 'class="mhome-cards"' not in html
    assert 'class="mhome-profile"' in html
    assert html.count('class="mhome-group"') == 2, html.count('class="mhome-group"')

    for rid in ('mhomeAvatar', 'mhomeName', 'mhomeRole', 'mhomeCredits',
                'mhomeThemeSwitch', 'mhomeLangValue', 'mhomeVersion',
                'mhomeRowAccount', 'mhomeRowApi'):
        assert f'id="{rid}"' in html, rid

    # 七个设置入口：账号 / 积分 / API / 黑夜 / 语言 / 更新 / 退出
    for fn in ('mobileOpenAccounts()', 'mobileOpenCredits()', 'mobileOpenApi()',
               'mobileToggleTheme()', 'mobileToggleLang()', 'mobileCheckUpdate()',
               'mobileLogout()'):
        assert f'onclick="{fn}"' in html, fn
    assert html.count('class="mhome-row') >= 7

    # 进一级页面要拉一次账号信息，否则名字/积分是空的
    show = html.split('function showMobileHome()', 1)[1].split('function hideMobileHome', 1)[0]
    assert 'renderMobileMe();' in show
    assert "fetch('/api/auth/me'" in html
    # 名字由接口填充：不能再挂 data-i18n（否则会被「未登录」盖回去）
    assert 'id="mhomeName" data-i18n' not in html

    # 账号 / 积分走壳内 iframe：整页跳转会连底部标签栏一起丢掉
    for page in ('accounts', 'credits'):
        assert f'<iframe id="frame-{page}"' in html, page
        assert f"'{page}'" in html.split('const PAGE_IDS =', 1)[1].split(';', 1)[0], page
    assert 'function mobileOpenShellPage(id)' in html
    assert 'function mobileOpenCredits() { mobileOpenShellPage(\'credits\'); }' in html
    assert 'function mobileOpenAccounts() { mobileOpenShellPage(\'accounts\'); }' in html
    assert "const MOBILE_SHELL_PAGES = [...MOBILE_TAB_PAGES, 'credits', 'accounts'];" in html

    # 底部第一个标签改成「我的」
    assert 'data-i18n="me.tab"' in html
    assert '"me.tab":' in read('static/js/i18n/common.js')


def test_i18n_keys():
    common = read('static/js/i18n/common.js')
    for key in ('home.title', 'home.subtitle', 'home.aiChat',
                'me.tab', 'me.notLoggedIn', 'me.account', 'me.credits',
                'me.language', 'me.update', 'me.logout'):
        assert f'"{key}":' in common, key
    # 每条都要中英双份
    for m in re.finditer(r'"((?:home|me)\.[A-Za-z]+)":\s*\{([^}]*)\}', common):
        assert 'zh:' in m.group(2) and 'en:' in m.group(2), m.group(1)


if __name__ == '__main__':
    test_index_shell()
    test_me_page()
    test_i18n_keys()
    print('OK mobile-portrait-home')
