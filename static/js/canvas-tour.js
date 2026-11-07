/* 画布新人引导（canvas tour）
 *
 * 目标（老板 m16915）：
 *  1. 先对整页区域做分类分布介绍，再逐块细化「有哪些功能 / 适合什么场景 / 处理哪类需求时来这块找」；
 *  2. 强制用户跟随操作走一遍：某一步需要真实操作（双击空白、点运行、拖节点、开关面板）才允许继续；
 *  3. 走到「要点运行 / 生成」这类真花钱的操作时，允许点「结束本段」直接进下一段；
 *  4. 每段开始前有一张「本段讲什么」的说明卡，可跳过，跳过后同样先说明下一段再开始；
 *  5. 每段起始步骤的功能处贴一个「?」小徽标，随时点开复习该段。
 *
 * 纯前端、零依赖。数据在 SEGMENTS，逻辑在下面。localStorage: ic_canvas_tour_v1
 * 调试参数：?tour=force 强制启动；?tour=off 本次禁用；?tour=reset 清记录后可重新自动触发。
 */
(function () {
    'use strict';

    if (window.__icCanvasTour) return;

    var LS_KEY = 'ic_canvas_tour_v1';
    var PARAMS = new URLSearchParams(location.search);

    var SEGMENTS = [
        /* ────────────────────────── 第一段：画布总览 ────────────────────────── */
        {
            id: 'overview',
            title: '画布总览',
            heading: '第一段 · 先认清画布的四块区域',
            badge: { sel: '#smartTitle', pos: 'tr', label: '复习：画布总览' },
            points: [
                '中央是画布，所有节点都摆在这里',
                '底部是输入栏，写提示词、调参数、点运行',
                '右侧是三扇门：AI Agent / 资产库 / 灵感库',
                '右下是小地图与整理按钮，左上角返回画布列表'
            ],
            intro: '这一段只做一件事：把画布分成四块认清楚，知道「东西放在哪、从哪开始、去哪找参考和助手」。看完大概 1 分钟，随时可以跳过，跳过不影响任何功能。',
            steps: [
                {
                    mode: 'center',
                    sel: '#world',
                    wait: { drag: true, hint: '按住鼠标中键拖一拖，或按住空格 + 左键拖动' },
                    title: '中央：无限画布',
                    body: '画面中间这一大片就是画布，所有东西都以「节点」的形式摆在这里：\n' +
                        '· 上传的图片 / 视频 / 音频 / 文档\n' +
                        '· 生成出来的结果\n' +
                        '· 提示词节点、分组、循环、3D 预览\n\n' +
                        '移动画布：按住鼠标中键拖动，或者按住空格 + 左键拖动（左键直接拖是框选）；滚轮缩放。\n\n' +
                        '画布没有边界，节点可以摆得很远，靠右下角的小地图找回它们。\n\n' +
                        '适合：把一条创作流程「摊开」——左边放参考素材，中间放生成器，右边放结果，一眼就能看出这组图是怎么来的。'
                },
                {
                    mode: 'center',
                    sel: '#world',
                    wait: { selector: '#composer.open', hint: '在画布上点一下任意一个节点（画布是空的就双击空白新建一个）' },
                    title: '先选中一个节点',
                    body: '节点就是画布上的每一张图、每一段视频、每一个提示词。\n\n' +
                        '点一下任意节点，它的边框会亮起 —— 这时候它下面的输入栏才会出现，接下来所有「跑模型」的操作都在那里。\n\n' +
                        '画布是空的？双击空白处新建一个，建完会自动选中。'
                },
                {
                    sel: '#composer',
                    pad: 12,
                    title: '底部：输入栏，所有生成的起点',
                    body: '输入栏跟着选中的节点走，它就是那个节点的控制台：\n' +
                        '· 写提示词（支持多行、@ 引用其它节点、粘贴/拖入参考图）\n' +
                        '· 调模型、比例、分辨率、张数\n' +
                        '· 点「运行」真正出图\n\n' +
                        '适合：改图、基于参考图再生成、批量出图 —— 只要要「跑一次模型」，都从这里发起。'
                },
                {
                    sel: '#assetToggle',
                    pad: 10,
                    wait: { click: '#assetToggle', hint: '点一下右上角的「资产库」，看一眼你自己的素材' },
                    title: '右上：资产库 / 灵感库 / 快捷键 / 日志',
                    body: '右上角这一排按钮各自打开一块面板，它们是「找素材、找参考、查问题」的入口：\n' +
                        '· 资产库：你上传和生成的素材，还能建风格库\n' +
                        '· 灵感库：按分类浏览参考图与提示词\n' +
                        '· 快捷键：所有操作的完整列表\n' +
                        '· 日志：每次运行的请求参数与报错\n\n' +
                        'AI Agent 是画布右侧那个对话窗，默认就开着，不用点按钮。\n\n' +
                        '适合：不知道从哪下手时问 Agent、缺素材时找资产库、缺感觉时找灵感库。'
                },
                {
                    sel: '#minimap',
                    pad: 10,
                    place: 'left',
                    wait: { click: '#minimap', hint: '在右下角的小地图上点一下，视图会跳过去' },
                    title: '右下：小地图与整理',
                    body: '· 小地图：整块画布的缩略图，点哪里就跳到哪里，节点变多以后靠它导航\n' +
                        '· 整理选中：把选中的一堆节点自动排整齐\n' +
                        '· 保存工作流：把选中的节点和连线存成模板，下次一键铺回来\n\n' +
                        '适合：画布乱了、节点找不到了、想把一套固定流程反复使用时。'
                },
                {
                    sel: '#smartTitle',
                    pad: 10,
                    place: 'bottom',
                    title: '左上：标题与返回画布列表',
                    body: '左上角的标题就是你当前这张画布的名字，画布列表（在浏览器返回或左上角返回按钮）里可以重命名、复制、删除。\n\n' +
                        '顶部还有「工作流」「日志」「快捷键」三颗按钮：查操作、看运行细节、管理你存下来的模板。'
                }
            ]
        },

        /* ────────────────────────── 第二段：新建 ────────────────────────── */
        {
            id: 'create',
            title: '新建与上传',
            heading: '第二段 · 怎么把东西放到画布上',
            badge: { sel: '#composer', pos: 'tr', at: [2, 2], label: '复习：新建与上传' },
            points: [
                '空白处双击（或右键）= 新建菜单',
                '菜单里 7 张卡片，覆盖上传 / 生成 / 提示词 / 分组 / 循环 / 视频 / 3D',
                '按需求选卡片，选完节点就落在画布上'
            ],
            intro: '这段讲「新建」。核心动作只有一个：在画布空白处双击，弹出新建菜单，选一张卡片。菜单里 7 张卡片各有用途，下面会逐张说清楚什么场合用哪张。',
            steps: [
                {
                    sel: '#world',
                    mode: 'center',
                    wait: { selector: '#createMenu.open', hint: '在画布空白处双击一下（右键空白也行）' },
                    title: '第一步：双击空白处',
                    body: '双击（或右键）画布空白处，新建菜单就会弹出来。\n\n' +
                        '注意：点在已有节点、面板、输入栏上不会弹出菜单 —— 这是防止误触，只有真正的空白区域才算。\n\n' +
                        '另外两种放东西的方式：把本地文件直接拖进画布、或者按 Ctrl+V 粘贴图片。'
                },
                {
                    sel: '#createMenu',
                    pad: 10,
                    wait: { click: '.create-card', hint: '看完点一张卡片（比如「上传」）—— 点完自动进入下一段', advance: true },
                    title: '新建菜单：7 张卡片分别干什么',
                    body: '· 上传：图片、视频、音频、文档都能传，传完变成素材节点，可以直接当参考图\n' +
                        '· 分组：把多张图收进一个组，组内成员能一起跑、一起改\n' +
                        '· 提示词节点：手写提示词，也能开 LLM 让模型帮你扩写或描述图片\n' +
                        '· 循环：控制跑几轮、每轮几张、变量替换，适合批量换装 / 换背景\n' +
                        '· MiniMax 视频：时间轴式多片段生成，适合有剧情的短视频\n' +
                        '· 3D 预览：把一张图变成能旋转的立体场景，检查构图和视角\n' +
                        '· 混元 3D：上传多视图生成真正的 3D 模型\n\n' +
                        '快速对照：想批量 → 循环；想复用提示词 → 提示词节点；想做视频 → MiniMax；想看立体 → 3D 预览。\n' +
                        '每张卡片右上角都有一个「?」，鼠标悬停能看到更细的说明。'
                }
            ]
        },

        /* ────────────────────────── 第三段：输入与生成 ────────────────────────── */
        {
            id: 'generate',
            title: '输入与生成',
            heading: '第三段 · 从一句话到一张图',
            badge: { sel: '#runBtn', pos: 'tl', label: '复习：输入与生成' },
            points: [
                '输入框写提示词：@ 引用节点、粘贴/拖入参考图',
                '四个小工具：模板库、历史、LLM 扩写、风格库',
                '参数行选模型、比例、分辨率、张数',
                '点「运行」出图，按钮上能看到本次消耗的积分'
            ],
            intro: '这段讲真正出图的通道：底部输入栏。写完提示词、调好参数、点运行，结果会作为新节点落在右侧。只要走到「点运行」这一步，你就可以点「结束本段」直接进下一段 —— 不必真的花积分生成。',
            steps: [
                {
                    sel: '#world',
                    mode: 'center',
                    wait: { selector: '#composer.open', hint: '在画布上点一下任意一个节点（还没有节点？双击空白新建一个）' },
                    title: '第一步：先选中一个节点',
                    body: '底部输入栏是跟着节点走的：选中哪个节点，输入栏就出现在它下面。\n\n' +
                        '所以写提示词之前，先在画布上点一个节点 —— 它会亮起边框，输入栏随即弹出。\n\n' +
                        '画布还是空的？双击空白处新建一个，建完会自动选中。'
                },
                {
                    sel: '#promptInput',
                    pad: 6,
                    wait: { input: { sel: '#promptInput', min: 2 }, hint: '在这个框里随便打两个字试试' },
                    title: '写提示词',
                    body: '现在输入栏已经出现了，在这个框里写你想要的画面。三个快捷用法：\n' +
                        '· 输入 @ 可以引用画布上任意节点（图片当参考图、文本当提示词）\n' +
                        '· 直接粘贴或把图片拖进来，会加到这一轮的参考图里\n' +
                        '· Shift + Enter 换行，长提示词分段写更清楚\n\n' +
                        '写不好也没关系，下一步的「LLM 扩写」可以帮你改写成专业提示词。'
                },
                {
                    sel: '.composer-prompt-tools',
                    pad: 6,
                    title: '四个小工具：模板、历史、LLM、风格',
                    body: '输入框左下角这四个按钮，解决「不会写提示词」：\n' +
                        '· 模板库：内置标准提示词 + 你自己的预设，点一下就填进来\n' +
                        '· 历史：最近用过的提示词，点一下回填，不用重复打字\n' +
                        '· LLM 扩写：把你的草稿交给模型改写成专业提示词，可选文生图 / 图生图 / H3 视频预设；扩写结果会出现在右侧输出栏\n' +
                        '· 风格库：从你建好的风格 Skill 里挑一个，自动带上风格描述和参考图\n\n' +
                        '适合：卡在措辞、想复用上次的写法、想让成片稳定在同一种风格上。'
                },
                {
                    sel: '#dynamicParams',
                    pad: 8,
                    title: '参数行：模型与尺寸',
                    body: '同一个输入框，参数决定出什么样的图：\n' +
                        '· 模型：不同通道能力不同（有的擅长文字、有的擅长写实、有的支持图生图）\n' +
                        '· 比例 / 分辨率：竖图适合人像和海报，横图适合场景和封面\n' +
                        '· 张数：一次出几张，满意哪张留哪张\n' +
                        '· 更多参数（随机种子、参考强度等）随模型不同而不同\n\n' +
                        '改完立刻生效，并会记在这个节点上，下次选中它还是这套参数。'
                },
                {
                    sel: '#runBtn',
                    pad: 8,
                    wait: { click: '#runBtn', hint: '想真跑就点「运行」；不想花积分，点下面的「结束本段」', advance: false },
                    allowEnd: true,
                    title: '点运行出图',
                    body: '点「运行」开始生成，按钮上会显示本次预计消耗的积分。生成期间你可以继续摆节点、调别的参数，结果出来会作为新节点落在右侧，并自动连好线。\n\n' +
                        '如果结果不满意：选中它 → 改提示词 → 再运行，就会在右侧再开一条分支，旧结果不会丢。\n\n' +
                        '想先了解后面的内容，直接点「结束本段」，一样会进入下一段。'
                }
            ]
        },

        /* ────────────────────────── 第四段：画布操作 ────────────────────────── */
        {
            id: 'canvas',
            title: '画布操作',
            heading: '第四段 · 手上功夫：拖、选、移、缩放、连线',
            badge: { sel: '#minimap', pos: 'in-bl', label: '复习：画布操作' },
            points: [
                '拖节点移动；拖空白框选；空格 + 左键平移；滚轮缩放',
                '节点边缘圆点是连线口，把上游接到下游',
                '整理选中自动排版，保存工作流存成模板'
            ],
            intro: '这段讲手上功夫。所有动作在「快捷键」面板里都能查到，忘了随时按左上角的「?」复习这一段。',
            steps: [
                {
                    sel: '#world',
                    mode: 'center',
                    wait: { drag: true, hint: '拖一个节点，或者在空白处拖出一个选框' },
                    title: '拖动 / 框选 / 平移 / 缩放',
                    body: '· 拖动节点：按住节点拖\n' +
                        '· 框选：在空白处按住左键拖出一个框，框住的都会被选中；Ctrl + 拖动是同样的框选\n' +
                        '· 平移画布：按住空格 + 左键拖，或者按住鼠标中键拖\n' +
                        '· 缩放：滚轮前后滚；Ctrl + 滚轮更精细\n' +
                        '· 删除：选中后按 Delete\n' +
                        '· 复制粘贴：Ctrl + C / Ctrl + V\n\n' +
                        '现在试一下：随便是拖个节点，还是在空白处拖个框，都算完成。'
                },
                {
                    sel: '#world',
                    mode: 'center',
                    title: '连线：把上游接给下游',
                    body: '每个节点边缘上的小圆点是「连接口」。把 A 右侧的圆点拖到 B 左侧的圆点上，就表示 B 会用到 A 的内容：\n' +
                        '· A 是图片 → B 把它当参考图\n' +
                        '· A 是提示词节点 → B 直接使用它的最终提示词\n' +
                        '· 拖到分组上 → 把 B 收进这个组\n\n' +
                        '连错了：按住连线中间把它拖开，或者选中连线按 Delete。\n\n' +
                        '这是整套画布最核心的用法：一串「参考图 → 生成器 → 结果」连起来，就是一条可复用的创作流水线。'
                },
                {
                    sel: '#smartArrangeBtn',
                    pad: 10,
                    place: 'left',
                    wait: { click: '#smartArrangeBtn', hint: '先框选两个以上节点，再点一下「整理选中」' },
                    title: '整理选中与保存工作流',
                    body: '· 整理选中：选中多个节点后点它，自动排成整齐的网格，连线也会重新走好\n' +
                        '· 保存工作流：把当前选中的节点 + 连线存成模板；下次在「工作流」面板里一键铺到画布上，参数和提示词都在\n\n' +
                        '适合：做完一套好用的流程想固化下来，或者节点摆乱了想一键归位。'
                }
            ]
        },

        /* ────────────────────────── 第五段：右侧面板 ────────────────────────── */
        {
            id: 'panels',
            title: '右侧面板',
            heading: '第五段 · 助手与素材：Agent、资产库、灵感库',
            badge: { sel: '#assetToggle', pos: 'tr', label: '复习：右侧面板' },
            points: [
                'AI Agent：用大白话搭流程（默认常驻在画布上）',
                '资产库：素材与风格库',
                '灵感库：参考图与提示词',
                '快捷键 / 日志 / 工作流收尾'
            ],
            intro: '最后一段：画布右侧那个对话窗是 AI Agent，右上角按钮打开资产库和灵感库。它们解决的是「不会写、缺素材、缺灵感」这三种最常见的卡壳。',
            steps: [
                {
                    sel: '#agentPanel',
                    pad: 8,
                    wait: { click: '#agentPanel', hint: '点一下这个对话窗（点到输入框更好，可以直接打字）' },
                    title: 'AI Agent：用人话搭流程',
                    body: '这个对话窗默认就贴在画布上，不用点按钮打开。用聊天的方式让它干活，比如「做一张国潮风格的海报，竖版 3:4」。它会自己：\n' +
                        '· 建生成器节点、填提示词、选比例\n' +
                        '· 需要参考图时主动问你要，或者引用你 @ 的节点\n' +
                        '· 出图后把结果直接落到画布上，并连好线\n\n' +
                        '几个省事的用法：\n' +
                        '· 输入 / 唤出命令面板（技能、快捷动作）\n' +
                        '· 输入 @ 引用画布上任意节点当上下文\n' +
                        '· 面板下方选比例和分辨率，说需求时不用重复交代\n\n' +
                        '适合：不想手动搭节点、或者说不清参数只想描述效果时。'
                },
                {
                    sel: '#assetToggle',
                    pad: 10,
                    wait: { click: '#assetToggle', hint: '点一下「资产库」按钮打开它' },
                    title: '资产库：素材与风格库',
                    body: '你自己上传和生成的东西都在这里，分「素材」和「风格库」两个页签：\n' +
                        '· 素材：可以上传、批量管理、选中 3~6 张 → 命名 → 直接建成一个风格\n' +
                        '· 风格库：每个风格 = 一组参考图 + 一段风格描述，生成时在输入栏的「风格」里选一下就能套用\n' +
                        '· 个人 / 团队：可以只给自己用，也能共享给团队\n\n' +
                        '适合：想统一一组图的画风、想反复用同一批参考素材时。'
                },
                {
                    sel: '#inspireToggle',
                    pad: 10,
                    wait: { click: '#inspireToggle', hint: '点一下「灵感库」按钮打开它' },
                    title: '灵感库：参考图与提示词',
                    body: '按分类浏览现成的参考图和提示词：灵感库里的描述可以直接拿来改，看到合适的构图就记住它的说法。\n\n' +
                        '适合：不知道该怎么形容画面、想找一个风格的表达方式时。\n\n' +
                        '小技巧：看到喜欢的图，先存进资产库，之后做风格库就有了现成的参考。'
                },
                {
                    sel: '#smartShortcutToggle',
                    pad: 8,
                    place: 'left',
                    title: '收尾：快捷键、日志、工作流',
                    body: '· 快捷键：所有操作的完整列表，也能从这里重新看新人引导\n' +
                        '· 日志：每次运行的请求、参数、报错 —— 出问题时先看这里，反馈问题时把这段发出来最快定位\n' +
                        '· 工作流：管理你保存的流程模板\n\n' +
                        '引导到这里结束。之后每个起始功能旁边都有一个「?」，随时点开复习对应那一段。祝你玩得顺手。'
                }
            ]
        }
    ];

    /* ────────────────────────────── 状态 ────────────────────────────── */
    var state = {
        running: false,
        seg: 0,
        step: 0,
        phase: 'intro',      // 'intro' | 'step'
        waitOk: false,
        waitTriggered: false,
        panels: null,
        noMore: false
    };

    var dom = { layer: null, tip: null, spot: null, frame: null, arrow: null, dims: {}, badges: [] };
    var pollTimer = null;
    var repositionTimer = null;
    var lastRect = null;
    var lastSpot = null;

    /* ────────────────────────────── 工具 ────────────────────────────── */
    function $(sel, root) {
        try { return (root || document).querySelector(sel); } catch (e) { return null; }
    }
    function $$(sel, root) {
        try { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); } catch (e) { return []; }
    }
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function loadStore() {
        try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; } catch (e) { return {}; }
    }
    function saveStore(patch) {
        var cur = loadStore();
        Object.keys(patch || {}).forEach(function (k) { cur[k] = patch[k]; });
        try { localStorage.setItem(LS_KEY, JSON.stringify(cur)); } catch (e) {}
        return cur;
    }
    function curSeg() { return SEGMENTS[state.seg] || null; }
    function curStep() {
        var seg = curSeg();
        return seg && seg.steps ? seg.steps[state.step] : null;
    }

    /* ────────────────────────────── DOM ────────────────────────────── */
    function ensureDom() {
        if (dom.layer && document.body.contains(dom.layer)) return;
        var layer = document.createElement('div');
        layer.className = 'ct-layer';
        layer.id = 'ctLayer';
        layer.innerHTML =
            '<div class="ct-dim" data-dim="top"></div>' +
            '<div class="ct-dim" data-dim="left"></div>' +
            '<div class="ct-dim" data-dim="right"></div>' +
            '<div class="ct-dim" data-dim="bottom"></div>' +
            '<div class="ct-spot" id="ctSpot"></div>' +
            '<div class="ct-frame" id="ctFrame"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>' +
            '<div class="ct-arrow" id="ctArrow"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
                '<path d="M12 19V5M12 5l-6 6M12 5l6 6" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' +
            '</svg></div>' +
            '<div class="ct-tip" id="ctTip" role="dialog" aria-live="polite"></div>';
        document.body.appendChild(layer);
        dom.layer = layer;
        dom.tip = layer.querySelector('#ctTip');
        dom.spot = layer.querySelector('#ctSpot');
        dom.frame = layer.querySelector('#ctFrame');
        dom.arrow = layer.querySelector('#ctArrow');
        ['top', 'left', 'right', 'bottom'].forEach(function (k) {
            dom.dims[k] = layer.querySelector('.ct-dim[data-dim="' + k + '"]');
        });

        dom.tip.addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-ct-act]');
            if (!btn || btn.disabled) return;
            var act = btn.getAttribute('data-ct-act');
            if (act === 'next') next();
            else if (act === 'prev') prev();
            else if (act === 'skip') skipSegment();
            else if (act === 'start') beginSegmentSteps();
            else if (act === 'quit') stop('quit');
            else if (act === 'finish') finish();
        });
        dom.tip.addEventListener('change', function (ev) {
            if (ev.target && ev.target.id === 'ctNoMore') state.noMore = !!ev.target.checked;
        });
    }

    /* ────────────────────────────── 徽标 ────────────────────────────── */
    function buildBadges() {
        removeBadges();
        SEGMENTS.forEach(function (seg, i) {
            if (!seg.badge || !seg.badge.sel) return;
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'ct-badge';
            b.setAttribute('data-ct-badge', seg.id);
            b.setAttribute('title', seg.badge.label || ('复习：' + seg.title));
            b.setAttribute('aria-label', seg.badge.label || ('复习：' + seg.title));
            b.textContent = '?';
            b.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                startAt(i);
            });
            document.body.appendChild(b);
            dom.badges.push({ el: b, seg: seg, index: i });
        });
        layoutBadges();
        window.addEventListener('resize', layoutBadges);
    }

    function removeBadges() {
        dom.badges.forEach(function (item) {
            if (item.el && item.el.parentNode) item.el.parentNode.removeChild(item.el);
        });
        dom.badges = [];
    }

    /* ──────────────────── 常驻「?」复习中心（左下） ────────────────────
     * 徽标要贴在某段起始功能上，但「新建」「输入栏」这类锚点会随 composer 收起而消失，
     * 所以另给一个永远在的入口：点开就是 5 段清单，任何一段都能直接重看。
     */
    var hub = { root: null, pop: null };

    function hideHubPop() {
        if (!hub.pop) return;
        hub.pop.hidden = true;
        if (hub.root) hub.root.classList.remove('ct-hub-open');
    }
    function showHubPop() {
        if (!hub.pop) return;
        hub.pop.hidden = false;
        if (hub.root) hub.root.classList.add('ct-hub-open');
    }
    function toggleHubPop() {
        if (!hub.pop) return;
        if (hub.pop.hidden) showHubPop(); else hideHubPop();
    }

    function buildHub() {
        if (hub.root && document.body.contains(hub.root)) return;
        var root = document.createElement('div');
        root.className = 'ct-hub';
        root.id = 'ctHub';
        var rows = SEGMENTS.map(function (seg, i) {
            return '<button type="button" class="ct-hub-row" data-seg="' + i + '">' +
                '<b>' + (i + 1) + ' · ' + esc(seg.title) + '</b>' +
                '<span>' + esc((seg.points && seg.points[0]) || seg.heading || '') + '</span>' +
                '</button>';
        }).join('');
        root.innerHTML =
            '<div class="ct-hub-pop" id="ctHubPop" hidden>' +
                '<div class="ct-hub-head"><span>新人引导 · 想复习哪一段？</span>' +
                    '<button type="button" class="ct-hub-close" data-hub-close="1" aria-label="关闭">×</button>' +
                '</div>' +
                '<div class="ct-hub-list">' + rows + '</div>' +
                '<div class="ct-hub-foot">' +
                    '<button type="button" class="ct-hub-restart" data-hub-restart="1">从头再看一遍</button>' +
                '</div>' +
            '</div>' +
            '<button type="button" class="ct-hub-btn" id="ctHubBtn" ' +
                'title="新人引导：点开可复习任意一段" aria-label="新人引导">?</button>';
        document.body.appendChild(root);
        hub.root = root;
        hub.pop = root.querySelector('#ctHubPop');

        root.addEventListener('click', function (ev) {
            var row = ev.target.closest('[data-seg]');
            if (row) {
                ev.preventDefault(); ev.stopPropagation();
                hideHubPop();
                startAt(parseInt(row.getAttribute('data-seg'), 10) || 0);
                return;
            }
            if (ev.target.closest('[data-hub-restart]')) {
                ev.preventDefault(); ev.stopPropagation();
                hideHubPop();
                try { localStorage.removeItem(LS_KEY); } catch (e) {}
                startAt(0);
                return;
            }
            if (ev.target.closest('[data-hub-close]') || ev.target.closest('#ctHubBtn')) {
                ev.preventDefault(); ev.stopPropagation();
                toggleHubPop();
            }
        });
        // 点面板外面收起
        document.addEventListener('click', function (ev) {
            if (!hub.pop || hub.pop.hidden) return;
            if (hub.root && hub.root.contains(ev.target)) return;
            hideHubPop();
        }, true);
    }

    // 徽标锚点：允许写数组，按顺序取第一个「看得见」的
    function badgeAnchor(seg) {
        var b = seg && seg.badge;
        if (!b) return null;
        var list = Array.isArray(b.sel) ? b.sel : (b.sel ? [b.sel] : []);
        for (var i = 0; i < list.length; i++) {
            var el = $(list[i]);
            if (el && isVisible(el)) return el;
        }
        return null;
    }

    function layoutBadges() {
        var running = state.running;
        document.body.classList.toggle('ct-running', running);
        dom.badges.forEach(function (item) {
            var el = item.el;
            var anchor = badgeAnchor(item.seg);
            var size = 19;
            var x, y;
            if (!anchor) {
                // 没有可见锚点时用固定落点（例如「双击空白新建」这种属于整块画布的功能）
                var at = item.seg.badge && item.seg.badge.at;
                if (!at) { el.classList.add('ct-badge-hide'); return; }
                el.removeAttribute('data-ct-anchor');
                el.classList.remove('ct-badge-hide');
                el.style.left = Math.round(at[0]) + 'px';
                el.style.top = Math.round(at[1]) + 'px';
                el.classList.add('ct-badge-on');
                return;
            }
            if (anchor.id) el.setAttribute('data-ct-anchor', '#' + anchor.id);
            var r = anchor.getBoundingClientRect();
            if (!r.width && !r.height) { el.classList.add('ct-badge-hide'); return; }
            el.classList.remove('ct-badge-hide');
            var pos = item.seg.badge.pos || 'tr';
            // 贴在目标外面，别压住目标本身的内容
            if (pos === 'tl') { x = r.left - size - 2; y = r.top - 8; }
            else if (pos === 'bl') { x = r.left - size - 2; y = r.bottom - size + 8; }
            else if (pos === 'br') { x = r.right + 2; y = r.bottom - size + 8; }
            else if (pos === 'in-bl') { x = r.left + 8; y = r.bottom - size - 8; }   // 贴在目标框内左下角
            else if (pos === 'in-br') { x = r.right - size - 8; y = r.bottom - size - 8; }
            else { x = r.right + 2; y = r.top - 8; }
            x = Math.max(2, Math.min(window.innerWidth - size - 2, x));
            y = Math.max(2, Math.min(window.innerHeight - size - 2, y));
            el.style.left = Math.round(x) + 'px';
            el.style.top = Math.round(y) + 'px';
            el.classList.add('ct-badge-on');
        });
    }

    /* ────────────────────────────── 定位 ────────────────────────────── */
    // 元素是否真的「看得见」：display:none / opacity:0（例如未选中节点时收起的 composer）
    // 一律当作不可见 —— 否则会对着空气打聚光灯、气泡也不知道往哪放。
    function isVisible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        var r = el.getBoundingClientRect();
        if (!r.width && !r.height) return false;
        // 逐层往上看：父级 opacity:0 / visibility:hidden / display:none 都不算「看得见」。
        // （子元素自己的 computed opacity 不会继承父级，只查自身会把收起的 composer 里的按钮当成可见）
        var node = el, guard = 0;
        while (node && node.nodeType === 1 && guard++ < 32) {
            try {
                var cs = window.getComputedStyle(node);
                if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                if (Number(cs.opacity) < 0.05) return false;
            } catch (e) { return false; }
            node = node.parentElement;
        }
        return true;
    }

    function rectOfEl(el, pad) {
        if (!el || !isVisible(el)) return null;
        var r = el.getBoundingClientRect();
        if (!r.width && !r.height) return null;
        var p = typeof pad === 'number' ? pad : 8;
        return {
            left: r.left - p,
            top: r.top - p,
            width: r.width + p * 2,
            height: r.height + p * 2
        };
    }

    function rectOf(step) {
        if (!step || !step.sel) return null;
        return rectOfEl($(step.sel), typeof step.pad === 'number' ? step.pad : 8);
    }

    function isBigRect(r) {
        if (!r) return true;
        return (r.width * r.height) > (window.innerWidth * window.innerHeight * 0.55);
    }

    function placeTip(rect, step, anchorRect) {
        var tip = dom.tip;
        if (!tip) return;
        tip.style.left = '0px';
        tip.style.top = '0px';
        tip.style.maxWidth = '';
        var tw = tip.offsetWidth || 392;
        var th = tip.offsetHeight || 240;
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var gap = 14;
        var margin = 12;

        // rect 现在是"高亮区"（永远存在）；anchorRect 是真正的元素矩形。
        // 高亮区高到几乎占满视口时才退回居中（极端窄窗）。
        if (!rect || (rect.height > vh - th - gap * 2 - margin * 2 && rect.width > vw * 0.8)) {
            var cx = Math.round((vw - tw) / 2);
            var cy = Math.round(Math.min(vh - th - margin, Math.max(margin, vh * 0.6)));
            tip.style.left = Math.max(margin, cx) + 'px';
            tip.style.top = cy + 'px';
            return;
        }

        var prefer = step.place || 'auto';
        var cands = [];
        if (prefer === 'left') cands.push('left');
        if (prefer === 'right') cands.push('right');
        if (prefer === 'bottom') cands.push('bottom');
        if (prefer === 'top') cands.push('top');
        ['right', 'left', 'bottom', 'top'].forEach(function (p) {
            if (cands.indexOf(p) === -1) cands.push(p);
        });

        for (var i = 0; i < cands.length; i++) {
            var p = cands[i];
            var x, y, ok = false;
            if (p === 'right') {
                x = rect.left + rect.width + gap;
                y = rect.top + Math.max(0, (rect.height - th) / 2);
                ok = x + tw + margin <= vw;
            } else if (p === 'left') {
                x = rect.left - gap - tw;
                y = rect.top + Math.max(0, (rect.height - th) / 2);
                ok = x >= margin;
            } else if (p === 'bottom') {
                x = rect.left + Math.max(0, (rect.width - tw) / 2);
                y = rect.top + rect.height + gap;
                ok = y + th + margin <= vh;
            } else {
                x = rect.left + Math.max(0, (rect.width - tw) / 2);
                y = rect.top - gap - th;
                ok = y >= margin;
            }
            if (ok) {
                tip.style.left = Math.round(Math.max(margin, Math.min(vw - tw - margin, x))) + 'px';
                tip.style.top = Math.round(Math.max(margin, Math.min(vh - th - margin, y))) + 'px';
                return;
            }
        }
        // 四边都放不下（高亮块很大或窗口很窄）：先试着把卡片收窄塞进左右空档，
        // 收窄也塞不进去，才挑剩余空间最大的一边硬放 —— 绝不退回到压在目标上的位置。
        var rightSpace = vw - margin - (rect.left + rect.width + gap);
        var leftSpace = rect.left - gap - margin;
        var sideSpace = Math.max(rightSpace, leftSpace);
        if (sideSpace >= 232) {
            var side = rightSpace >= leftSpace ? 'right' : 'left';
            tip.style.maxWidth = Math.round(sideSpace) + 'px';
            tw = tip.offsetWidth || Math.min(392, sideSpace);
            th = tip.offsetHeight || th;
            var sx = side === 'right' ? rect.left + rect.width + gap : rect.left - gap - tw;
            var sy = rect.top + Math.max(0, (rect.height - th) / 2);
            tip.style.left = Math.round(Math.max(margin, Math.min(vw - tw - margin, sx))) + 'px';
            tip.style.top = Math.round(Math.max(margin, Math.min(vh - th - margin, sy))) + 'px';
            return;
        }
        var best = null, bestScore = -Infinity;
        ['right', 'left', 'bottom', 'top'].forEach(function (p) {
            var x, y, score;
            if (p === 'right') {
                x = rect.left + rect.width + gap;
                y = rect.top + Math.max(0, (rect.height - th) / 2);
                score = vw - margin - (x + tw);
            } else if (p === 'left') {
                x = rect.left - gap - tw;
                y = rect.top + Math.max(0, (rect.height - th) / 2);
                score = x - margin;
            } else if (p === 'bottom') {
                x = rect.left + Math.max(0, (rect.width - tw) / 2);
                y = rect.top + rect.height + gap;
                score = vh - margin - (y + th);
            } else {
                x = rect.left + Math.max(0, (rect.width - tw) / 2);
                y = rect.top - gap - th;
                score = y - margin;
            }
            if (score > bestScore) { bestScore = score; best = { x: x, y: y }; }
        });
        tip.style.left = Math.round(Math.max(margin, Math.min(vw - tw - margin, best.x))) + 'px';
        tip.style.top = Math.round(Math.max(margin, Math.min(vh - th - margin, best.y))) + 'px';
    }

    /* ── 高亮区计算 ────────────────────────────────────────────────
     * 每一步都必须有高亮区，否则整屏压暗后又没有任何提亮，用户只看到一张卡片。
     * mode:'center'（讲画布本身）或锚点不可见时，用一块"英雄框"代替：先把目标
     * clamp 进视口，再收成居中的舒适尺寸，既保留压暗的对比，又不会整屏都亮。 */
    function clampRect(r) {
        var vw = window.innerWidth, vh = window.innerHeight;
        var left = Math.max(0, Math.min(vw - 40, r.left));
        var top = Math.max(0, Math.min(vh - 40, r.top));
        var width = Math.max(40, Math.min(r.width, vw - left));
        var height = Math.max(40, Math.min(r.height, vh - top));
        return { left: left, top: top, width: width, height: height };
    }

    function heroRect(base) {
        var vw = window.innerWidth, vh = window.innerHeight;
        // 偏左偏上的英雄框：右侧/下方留出空间给气泡，避免白卡盖住要看的区域
        var w0 = Math.round(Math.min(vw * 0.56, 900));
        var h0 = Math.round(Math.min(vh * 0.5, 560));
        var left0 = Math.round(Math.max(24, vw * 0.06));
        var top0 = Math.round(Math.max(56, vh * 0.12));
        if (!base) {
            return { left: left0, top: top0, width: w0, height: h0 };
        }
        var r = clampRect(base);
        var w = Math.min(r.width, w0);
        var h = Math.min(r.height, h0);
        // 元素本身够小：围着它取景；元素很大（画布本体）：贴在左上方那块
        var cx = r.width <= w0 ? r.left + (r.width - w) / 2 : left0;
        var cy = r.height <= h0 ? r.top + (r.height - h) / 2 : top0;
        return {
            left: Math.round(Math.max(12, Math.min(vw - w - 12, cx))),
            top: Math.round(Math.max(48, Math.min(vh - h - 12, cy))),
            width: Math.round(w),
            height: Math.round(h)
        };
    }

    function spotRectFor(rect, step) {
        if (!rect) return heroRect(null);
        var r = clampRect(rect);
        if ((step && step.mode === 'center') || isBigRect(r)) return heroRect(r);
        return { left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) };
    }

    function layoutDim(r) {
        var vw = window.innerWidth, vh = window.innerHeight;
        var right = r.left + r.width;
        var bottom = r.top + r.height;
        var boxes = {
            top: { left: 0, top: 0, width: vw, height: Math.max(0, r.top) },
            bottom: { left: 0, top: bottom, width: vw, height: Math.max(0, vh - bottom) },
            left: { left: 0, top: r.top, width: Math.max(0, r.left), height: r.height },
            right: { left: right, top: r.top, width: Math.max(0, vw - right), height: r.height }
        };
        Object.keys(boxes).forEach(function (k) {
            var el = dom.dims[k];
            var b = boxes[k];
            if (!el) return;
            el.style.left = Math.round(b.left) + 'px';
            el.style.top = Math.round(b.top) + 'px';
            el.style.width = Math.round(b.width) + 'px';
            el.style.height = Math.round(b.height) + 'px';
        });
    }

    function setBox(el, r) {
        if (!el) return;
        el.style.left = r.left + 'px';
        el.style.top = r.top + 'px';
        el.style.width = r.width + 'px';
        el.style.height = r.height + 'px';
    }

    function radiusFor(r, step) {
        var el = step && step.sel ? $(step.sel) : null;
        if (el && el.classList.contains('composer')) return 20;
        return Math.min(18, Math.round(Math.min(r.width, r.height) * 0.08));
    }

    function syncSpot(rect, step) {
        var spot = dom.spot, frame = dom.frame;
        if (!spot) return;
        var r = spotRectFor(rect, step || {});
        lastSpot = r;
        layoutDim(r);
        setBox(spot, r);
        spot.style.borderRadius = radiusFor(r, step || {}) + 'px';
        if (frame) {
            setBox(frame, r);
            frame.style.borderRadius = spot.style.borderRadius;
        }
        ['top', 'left', 'right', 'bottom'].forEach(function (k) {
            if (dom.dims[k]) dom.dims[k].classList.remove('ct-off');
        });
        spot.classList.remove('ct-off');
        if (frame) frame.classList.remove('ct-off');
    }

    /* 指示符：从气泡指向高亮区中心，按主轴方向旋转箭头 */
    function syncArrow(r) {
        var arrow = dom.arrow;
        if (!arrow || !dom.tip || !r) return;
        var tr = dom.tip.getBoundingClientRect();
        if (!tr.width && !tr.height) { arrow.classList.add('ct-off'); return; }
        var tipX = tr.left + tr.width / 2;
        var tipY = tr.top + tr.height / 2;
        var cx = r.left + r.width / 2;
        var cy = r.top + r.height / 2;
        var dx = cx - tipX;
        var dy = cy - tipY;
        var size = 30;
        var x, y, deg;
        if (Math.abs(dx) > Math.abs(dy)) {
            // 目标在左/右
            deg = dx > 0 ? 90 : -90;
            x = dx > 0 ? (r.left - size - 10) : (r.left + r.width + 10);
            y = Math.min(Math.max(r.top + r.height / 2, 28), window.innerHeight - 28) - size / 2;
            if (Math.abs(dx) < (r.width / 2 + 60)) { arrow.classList.add('ct-off'); return; }
        } else {
            deg = dy > 0 ? 180 : 0;
            x = Math.min(Math.max(cx, 28), window.innerWidth - 28) - size / 2;
            y = dy > 0 ? (r.top + r.height + 10) : (r.top - size - 10);
            if (Math.abs(dy) < (r.height / 2 + 55)) { arrow.classList.add('ct-off'); return; }
        }
        x = Math.max(8, Math.min(window.innerWidth - size - 8, x));
        y = Math.max(8, Math.min(window.innerHeight - size - 8, y));
        arrow.classList.remove('ct-off');
        arrow.style.left = Math.round(x) + 'px';
        arrow.style.top = Math.round(y) + 'px';
        arrow.style.transform = 'rotate(' + deg + 'deg)';
    }

    function hideSpot() {
        if (dom.spot) dom.spot.classList.add('ct-off');
        if (dom.frame) dom.frame.classList.add('ct-off');
        if (dom.arrow) dom.arrow.classList.add('ct-off');
        Object.keys(dom.dims).forEach(function (k) {
            if (dom.dims[k]) dom.dims[k].classList.add('ct-off');
        });
    }

    function reposition() {
        if (!state.running) return;
        var step = curStep();
        // 段落预告卡：只压暗、不挖洞 —— 这一段还没有要指的控件，亮区会分散注意力。
        if (state.phase !== 'step') {
            lastRect = null;
            lastSpot = null;
            hideSpot();
            layoutDimFull();
            placeTip(null, step || {}, null);
            layoutBadges();
            return;
        }
        /* Agent 面板默认收纳在屏幕底部（老板 m20916）：讲到它的时候先滑出来，
           否则高亮区只是底边一条 54px 的缝，用户看不出这是在指对话窗。 */
        if (step && step.sel === '#agentPanel') untuckAgent();
        var rect = rectOf(step);
        lastRect = rect;
        syncSpot(rect, step || {});
        placeTip(lastSpot, step || {}, rect);
        syncArrow(lastSpot);
        layoutBadges();
    }

    // 没有高亮区时压暗整屏
    function layoutDimFull() {
        var vw = window.innerWidth, vh = window.innerHeight;
        var el = dom.dims.top;
        if (!el) return;
        ['left', 'right', 'bottom'].forEach(function (k) {
            var d = dom.dims[k];
            if (d) { d.style.width = '0px'; d.style.height = '0px'; d.classList.add('ct-off'); }
        });
        el.classList.remove('ct-off');
        el.style.left = '0px';
        el.style.top = '0px';
        el.style.width = vw + 'px';
        el.style.height = vh + 'px';
    }

    /* ────────────────────────────── 渲染 ────────────────────────────── */
    function dotsHtml(seg) {
        var html = '';
        var total = seg.steps.length;
        for (var i = 0; i < total; i++) {
            html += '<span class="ct-dot' + (state.phase === 'step' && i === state.step ? ' on' : '') + '"></span>';
        }
        return html;
    }

    function renderIntro() {
        var seg = curSeg();
        if (!seg) return;
        var idx = state.seg + 1;
        var points = (seg.points || []).map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('');
        dom.tip.innerHTML =
            '<div class="ct-head"><span class="ct-seg">第 ' + idx + ' / ' + SEGMENTS.length + ' 段 · 本段预告</span>' +
                '<button class="ct-x" data-ct-act="quit" title="退出引导">✕</button></div>' +
            '<div class="ct-title">' + esc(seg.heading) + '</div>' +
            '<div class="ct-body">' + esc(seg.intro) + '</div>' +
            (points ? '<ul class="ct-points">' + points + '</ul>' : '') +
            '<div class="ct-actions">' +
                '<button class="ct-btn ct-primary" data-ct-act="start">开始这一段</button>' +
                '<button class="ct-btn" data-ct-act="skip">跳过这段</button>' +
                '<span style="flex:1"></span>' +
                '<button class="ct-btn ct-ghost" data-ct-act="quit">退出引导</button>' +
            '</div>' +
            '<div class="ct-foot"><label><input type="checkbox" id="ctNoMore"' + (state.noMore ? ' checked' : '') + '>以后不再自动显示引导</label></div>';
    }

    function renderStep() {
        var seg = curSeg();
        var step = curStep();
        if (!seg || !step) return;
        var isLastStep = state.step >= seg.steps.length - 1;
        var isLastSeg = state.seg >= SEGMENTS.length - 1;
        var wait = step.wait;
        var waitHtml = '';
        if (wait && wait.hint) {
            var done = state.waitOk;
            waitHtml = '<div class="ct-wait' + (done ? ' is-on is-done' : ' is-on') + '">' +
                '<span class="ct-wait-dot"></span>' +
                '<span>' + (done ? '已完成，自动继续…' : esc(wait.hint)) + '</span></div>';
        }
        var primaryLabel;
        if (isLastStep && isLastSeg) primaryLabel = '完成引导';
        else if (isLastStep) primaryLabel = '下一段';
        else primaryLabel = '下一步';

        // 没有强制操作的步骤：明确告诉用户"这一屏看完点哪里"，避免卡住不知道怎么办
        if (!wait) {
            waitHtml = '<div class="ct-wait is-on is-idle">' +
                '<span class="ct-wait-dot"></span>' +
                '<span>这一步不用动手，看完点「' + primaryLabel + '」继续</span></div>';
        }

        var actions = '';
        if (state.step > 0) actions += '<button class="ct-btn ct-ghost" data-ct-act="prev">上一步</button>';
        actions += '<button class="ct-btn ct-primary" data-ct-act="' + (isLastStep && isLastSeg ? 'finish' : 'next') + '"' +
            (wait && !state.waitOk ? ' disabled' : '') + '>' + primaryLabel + '</button>';
        if (step.allowEnd) actions += '<button class="ct-btn" data-ct-act="next">结束本段</button>';
        actions += '<span style="flex:1"></span>';
        // 任何一步都能跳过本段：带强制操作的步骤如果卡住（比如不想真的传图），
        // 至少还有出口，不必退出整条引导。
        actions += '<button class="ct-btn ct-ghost" data-ct-act="skip">跳过本段</button>';

        dom.tip.innerHTML =
            '<div class="ct-head"><span class="ct-seg">第 ' + (state.seg + 1) + ' / ' + SEGMENTS.length + ' 段 · ' +
                esc(seg.title) + ' · 第 ' + (state.step + 1) + '/' + seg.steps.length + ' 步</span>' +
                '<button class="ct-x" data-ct-act="quit" title="退出引导">✕</button></div>' +
            '<div class="ct-title">' + esc(step.title) + '</div>' +
            '<div class="ct-body">' + esc(step.body) + '</div>' +
            waitHtml +
            '<div class="ct-actions"><span class="ct-dots">' + dotsHtml(seg) + '</span>' + actions + '</div>';
    }

    function render() {
        ensureDom();
        if (!state.running) return;
        dom.layer.classList.add('ct-on');
        if (state.phase === 'intro') renderIntro();
        else renderStep();
        // 气泡内容变了，尺寸也变了，重新摆一次
        requestAnimationFrame(reposition);
    }

    /* ────────────────────────────── 强制操作 ────────────────────────────── */
    function waitSatisfied(wait) {
        if (!wait) return false;
        if (wait.selector) return !!$(wait.selector);
        if (wait.input) {
            var el = $(wait.input.sel || '#promptInput');
            if (!el) return false;
            var text = (el.innerText || el.textContent || el.value || '').trim();
            return text.length >= (wait.input.min || 1);
        }
        // click / drag 由事件监听置位
        return !!state.waitTriggered;
    }

    function checkWait() {
        if (!state.running || state.phase !== 'step') return;
        var step = curStep();
        if (!step || !step.wait) return;
        var ok = waitSatisfied(step.wait);
        if (ok === state.waitOk) return;
        state.waitOk = ok;
        render();
        if (ok && step.wait.advance !== false) {
            setTimeout(function () {
                if (!state.running || state.phase !== 'step' || !state.waitOk) return;
                next();
            }, 460);
        }
    }

    function resetWait() {
        state.waitOk = false;
        state.waitTriggered = false;
    }

    function onDocClick(ev) {
        if (!state.running || state.phase !== 'step') return;
        var step = curStep();
        if (!step || !step.wait || !step.wait.click) return;
        var t = ev.target;
        if (!t || !t.closest) return;
        if (t.closest(step.wait.click)) {
            state.waitTriggered = true;
            checkWait();
        }
    }

    var dragWatch = null;
    function onPointerDown(ev) {
        if (!state.running || state.phase !== 'step') return;
        var step = curStep();
        if (!step || !step.wait || !step.wait.drag) return;
        var t = ev.target;
        if (!t || !t.closest) return;
        if (!t.closest('#world')) return;
        dragWatch = { x: ev.clientX, y: ev.clientY, moved: false };
    }
    function onPointerMove(ev) {
        if (!dragWatch || !state.running) return;
        var dx = Math.abs(ev.clientX - dragWatch.x);
        var dy = Math.abs(ev.clientY - dragWatch.y);
        if (dx + dy > 14) {
            dragWatch.moved = true;
            state.waitTriggered = true;
            checkWait();
        }
    }
    function onPointerUp() { dragWatch = null; }

    /* ────────────────────────────── 流程 ────────────────────────────── */
    function beginSegmentSteps() {
        state.phase = 'step';
        state.step = 0;
        resetWait();
        render();
    }

    function next() {
        var seg = curSeg();
        if (!seg) return stop('quit');
        if (state.phase === 'intro') return beginSegmentSteps();
        if (state.step < seg.steps.length - 1) {
            state.step += 1;
            resetWait();
            render();
            return;
        }
        // 本段结束
        saveStore({ done: Object.assign({}, loadStore().done || {}, { [seg.id]: true }) });
        if (state.seg < SEGMENTS.length - 1) {
            state.seg += 1;
            state.phase = 'intro';
            state.step = 0;
            resetWait();
            render();
        } else {
            finish();
        }
    }

    function prev() {
        if (state.phase === 'intro') {
            if (state.seg > 0) { state.seg -= 1; state.phase = 'step'; state.step = (curSeg().steps.length - 1); resetWait(); render(); }
            return;
        }
        if (state.step > 0) {
            state.step -= 1;
            resetWait();
            render();
            return;
        }
        // 回到本段说明卡
        state.phase = 'intro';
        resetWait();
        render();
    }

    function skipSegment() {
        var seg = curSeg();
        if (!seg) return stop('quit');
        if (state.seg < SEGMENTS.length - 1) {
            state.seg += 1;
            state.phase = 'intro';
            state.step = 0;
            resetWait();
            render();
        } else {
            finish();
        }
    }

    function finish() {
        saveStore({ completed: true, done: {} });
        stop('finish');
    }

    function snapshotPanels() {
        var ids = ['assetPanel', 'inspirePanel', 'agentPanel'];
        state.panels = ids.map(function (id) {
            var el = document.getElementById(id);
            return { id: id, open: !!(el && el.classList.contains('open')) };
        });
        /* Agent 面板默认是「底部收纳」态（老板 m20916）：只有 54px 一条，
           讲它的时候必须先滑出来，否则高亮区只是一条边缝。记一下原状，结束还原。 */
        var ap = document.getElementById('agentPanel');
        state.agentTucked = !!(ap && ap.classList.contains('agent-tucked'));
    }

    function untuckAgent() {
        if (typeof window.agentSetTucked !== 'function') return;
        try { window.agentSetTucked(false); } catch (e) {}
    }

    function restorePanels() {
        if (!state.panels) return;
        state.panels.forEach(function (p) {
            if (p.open) return;             // 引导前就是开的，保持原样
            var el = document.getElementById(p.id);
            if (!el || !el.classList.contains('open')) return;
            // 必须走页面自己的开关函数，否则面板内部状态（agentOpen/assetLibraryOpen/inspireOpen）
            // 会和 class 不同步，之后点按钮要按两次才生效。
            try {
                if (p.id === 'agentPanel' && typeof window.toggleAgentPanel === 'function') return window.toggleAgentPanel(false);
                if (p.id === 'assetPanel' && typeof window.toggleAssetLibrary === 'function') return window.toggleAssetLibrary(false);
                if (p.id === 'inspirePanel' && typeof window.toggleInspirePanel === 'function') return window.toggleInspirePanel(false);
            } catch (e) {}
            el.classList.remove('open');
        });
        state.panels = null;
        // 引导结束后把 Agent 面板还原成它原来的收纳状态
        if (state.agentTucked && typeof window.agentApplyDefaultBottomTuck === 'function') {
            try { window.agentApplyDefaultBottomTuck(); } catch (e) {}
        }
        state.agentTucked = false;
    }

    function startAt(segIndex) {
        ensureDom();
        if (!state.running) {
            snapshotPanels();
            state.running = true;
            document.addEventListener('click', onDocClick, true);
            document.addEventListener('pointerdown', onPointerDown, true);
            document.addEventListener('pointermove', onPointerMove, true);
            document.addEventListener('pointerup', onPointerUp, true);
            window.addEventListener('resize', reposition);
            pollTimer = setInterval(function () { checkWait(); }, 220);
            repositionTimer = setInterval(function () { reposition(); }, 420);
        }
        state.seg = Math.max(0, Math.min(SEGMENTS.length - 1, segIndex || 0));
        state.phase = 'intro';
        state.step = 0;
        state.noMore = false;
        resetWait();
        render();
        layoutBadges();
    }

    function stop(reason) {
        if (!state.running) return;
        state.running = false;
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        if (repositionTimer) { clearInterval(repositionTimer); repositionTimer = null; }
        document.removeEventListener('click', onDocClick, true);
        document.removeEventListener('pointerdown', onPointerDown, true);
        document.removeEventListener('pointermove', onPointerMove, true);
        document.removeEventListener('pointerup', onPointerUp, true);
        window.removeEventListener('resize', reposition);
        if (dom.layer) {
            dom.layer.classList.remove('ct-on');
            if (dom.tip) dom.tip.innerHTML = '';
        }
        hideSpot();
        lastSpot = null;
        document.body.classList.remove('ct-running');
        // 引导里为了演示开关过的面板，收尾时还原成引导前的样子
        restorePanels();
        if (state.noMore) saveStore({ completed: true, done: {} });
        layoutBadges();
    }

    function autoStart() {
        if (PARAMS.get('tour') === 'off') return;
        if (PARAMS.get('tour') === 'reset') {
            try { localStorage.removeItem(LS_KEY); } catch (e) {}
        }
        var force = PARAMS.get('tour') === 'force';
        var store = loadStore();
        if (!force && store.completed) return;
        // 等画布首帧、面板就位再开始，避免高亮位置为 0；
        // 首次使用还会弹「先花 30 秒认识一下你」偏好弹窗，等它关掉再开始，两条引导不打架。
        setTimeout(function () { waitProfileThenStart(force ? 0 : 1); }, force ? 600 : 1500);
    }

    function profileModalOpen() {
        var el = document.getElementById('agentProfileModal');
        if (!el) return false;
        if (el.hidden) return false;
        var r = el.getBoundingClientRect();
        return !!(r.width || r.height);
    }

    function waitProfileThenStart(tries) {
        if (state.running) return;
        if (profileModalOpen() && tries < 120) {
            setTimeout(function () { waitProfileThenStart(tries + 1); }, 500);
            return;
        }
        // ?tour=force&seg=2 可直接跳到第 N 段（1 起数），方便演示与自查
        var jump = parseInt(PARAMS.get('seg') || '', 10);
        startAt(isFinite(jump) && jump > 1 ? jump - 1 : 0);
    }

    function boot() {
        buildBadges();
        buildHub();
        autoStart();
        // 页面内其它脚本可能晚一步渲染，徽标位置再兜一次
        setTimeout(layoutBadges, 1200);
        setTimeout(layoutBadges, 2600);
    }

    window.icCanvasTour = {
        start: startAt,
        restart: function () {
            try { localStorage.removeItem(LS_KEY); } catch (e) {}
            return startAt(0);
        },
        next: next,
        prev: prev,
        skip: skipSegment,
        stop: stop,
        segments: SEGMENTS,
        state: state
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
