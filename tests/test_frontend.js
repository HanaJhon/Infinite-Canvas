'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
function load(name, values = {}) {
    const scope = vm.createContext(values);
    scope.window = scope;
    vm.runInContext(fs.readFileSync(path.join(root, 'static/js', name), 'utf8'), scope, {filename:name});
    return scope;
}

async function main() {
    const layers = load('split-layers.js');
    for (const name of ['openSplitLayersEditor', 'splitLayersApplyResult', 'splitLayersExportPsd', 'splitLayersToCanvas']) {
        assert.equal(vm.runInContext(`typeof ${name}`, layers), 'function', name);
    }
    const boxes = vm.runInContext(`(() => {
        splitLayersState.canvas = {width:640, height:480};
        const text = {kind:'text', textMode:'edit', bbox:[20,30,120,40], rotation:15};
        splitLayersEnsureEditable(text);
        const original = JSON.stringify(text.edit);
        text.edit.tx = 12;
        splitLayersEnsureEditable(text);
        return JSON.stringify({box:text.box, tx:text.edit.tx, initial:text.editInit.tx,
            pixel:splitLayersBoxFor({...text, textMode:'pixel', url:'/output/backup.png'}),
            transform:splitLayersTransformCss({tx:1,ty:2,rotate:15,scale:2,sx:0.5,sy:1})});
    })()`, layers);
    assert.deepEqual(JSON.parse(boxes), {
        box:{x:20,y:30,w:120,h:40}, tx:12, initial:0,
        pixel:{x:0,y:0,w:640,h:480},
        transform:'translate(1px, 2px) rotate(15deg) scale(1, 2)'
    });
    layers.document = {getElementById:() => null};
    layers.tr = key => key;
    layers.trf = key => key;
    assert.equal(vm.runInContext('splitLayersGptGateOpen()', layers), true,
        'product entry must work without a provider');
    const mappings = JSON.parse(vm.runInContext(`(() => {
        const layer = {kind:'element', bbox:[20,30,80,60]};
        splitLayersEnsureEditable(layer);
        layer.edit = {tx:17,ty:-11,rotate:37,scale:1.8,sx:.6,sy:1.4,opacity:1};
        const source = {x:25,y:70};
        const visible = splitLayersMapPoint(layer, source);
        const back = splitLayersMapPoint(layer, visible, true);
        const fresh = splitLayersMergeMaskLayer(layer, {...layer,bbox:[10,20,105,80]});
        const after = splitLayersMapPoint(fresh, source);
        const text = {kind:'text',text:'old',bbox:[0,0,120,40],font_size:24};
        const fit = splitLayersTextFit(text,{l:0,r:90,t:0,b:30}).k;
        text.text = 'a much longer new message';
        const edited = splitLayersTextFit(text,{l:0,r:400,t:0,b:30}).k;
        splitLayersState.maskStrokes = [{mode:'exclude',points:[[1,1,2]]},{mode:'include',points:[[1,1,1]]}];
        splitLayersUndoMask();
        const remaining = splitLayersState.maskStrokes.length;
        splitLayersUndoMask(true);
        return JSON.stringify({back,visible,after,fit,edited,remaining,
            modes:splitLayersState.maskStrokes.map(s=>s.mode)});
    })()`, layers));
    assert.ok(Math.abs(mappings.back.x - 25) < 1e-8 && Math.abs(mappings.back.y - 70) < 1e-8);
    assert.ok(Math.abs(mappings.visible.x - mappings.after.x) < 1e-8
        && Math.abs(mappings.visible.y - mappings.after.y) < 1e-8,
        'changing mask bbox must preserve the displayed transform');
    assert.equal(mappings.fit, mappings.edited, 'editing copy must not refit the old box');
    assert.equal(mappings.remaining, 1);
    assert.deepEqual(mappings.modes, ['exclude','include']);
    const restoredBox=vm.runInContext(`splitLayersEnsureEditable({
        kind:'text',bbox:[10,20,30,40],edit:{tx:12,ty:0,rotate:0,scale:1,sx:1,sy:1}
    }).box.x`,layers);
    assert.equal(restoredBox,10,'an old record with edits but no box can export immediately');
    // A real, synthetic Type-layer PSD exported and reopened in Photopea.
    const fixture=fs.readFileSync(path.join(__dirname,'fixtures/native-text.psd'));
    const matrix=[.9,.2,-.3,1.2,50,70];
    layers.psdFixture=Uint8Array.from(fixture).buffer;
    layers.psdMatrix=matrix;
    const patched=Buffer.from(vm.runInContext(`splitLayersPatchTextTransforms(psdFixture,[
        {name:'SL_title_Synthetic text',matrix:psdMatrix}])`,layers));
    const offset=fixture.indexOf(Buffer.from('8BIMTySh'))+14;
    assert.ok(offset>14,'fixture must contain one native text descriptor');
    matrix.forEach((value,i)=>assert.equal(patched.readDoubleBE(offset+i*8),value));
    assert.deepEqual(patched.subarray(0,offset),fixture.subarray(0,offset));
    assert.deepEqual(patched.subarray(offset+48),fixture.subarray(offset+48),
        'transform patch must not change any other PSD byte');
    assert.throws(()=>vm.runInContext('splitLayersPatchTextTransforms(psdFixture,[])',layers),
        /count mismatch|transform/);
    assert.throws(()=>vm.runInContext('splitLayersPatchTextTransforms(psdFixture.slice(0,50),[psdMatrix])',layers),
        /Invalid PSD/);
    vm.runInContext(`splitLayersState.layers = [
        {id:'subject', kind:'element', url:'fixture',bbox:[20,30,80,60]},
        {id:'reference',kind:'element',url:'original',bbox:[0,0,640,480],hidden:true}
    ]; splitLayersLoadImage = async url => url;`, layers);
    const draws = [];
    const ctx = {
        save(){}, restore(){}, translate(){}, rotate(){}, scale(){},
        drawImage(...args){ draws.push(args); }
    };
    layers.testCtx = ctx;
    await vm.runInContext('splitLayersCompositeTo(testCtx,640,480)', layers);
    assert.deepEqual(draws, [['fixture',0,0,640,480]],
        'full-size plates export at document origin and exclude the hidden reference');
    vm.runInContext('splitLayersLoadImage = async () => { throw new Error("missing asset") }', layers);
    await assert.rejects(vm.runInContext('splitLayersCompositeTo(testCtx,640,480)', layers),
        /missing asset/, 'export must fail instead of silently omitting a layer');

    const sockets = [];
    const timers = [];
    const received = [];
    let unload;
    class Socket {
        constructor(url) { this.url = url; sockets.push(this); }
        close() { this.onclose?.(); }
    }
    const sync = load('canvas-sync.js', {
        location:{host:'[::1]:3010', protocol:'https:'}, WebSocket:Socket,
        setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {},
        addEventListener(name, fn) { if(name === 'beforeunload') unload = fn; }
    });
    const stop = sync.startCanvasSyncSocket({clientId:'canvas id', onMessage:value => received.push(value)});
    assert.equal(sockets[0].url, 'wss://[::1]:3010/ws/stats?client_id=canvas%20id');
    sockets[0].onmessage({data:'invalid'});
    sockets[0].onmessage({data:'{"type":"canvas_updated"}'});
    assert.equal(received.length, 1);
    assert.equal(received[0].type, 'canvas_updated');
    sockets[0].close();
    assert.equal(timers.length, 1);
    timers[0]();
    assert.equal(sockets.length, 2);
    stop();
    unload();
    assert.equal(timers.length, 1, 'stopped sockets must not reconnect');

    for (const serverHasToken of [true, false]) {
        const tokens = load('modelscope-token.js', {
            localStorage:{getItem() { return 'browser-test-value'; }},
            fetch:async () => ({ok:true, json:async () => ({has_token:serverHasToken})})
        });
        const state = await tokens.getModelScopeTokenState();
        assert.equal(state.hasToken, true);
        assert.equal(state.apiKey, serverHasToken ? '' : 'browser-test-value');
    }
    console.log('frontend ok: layer module, transforms, websocket lifecycle, token state');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
