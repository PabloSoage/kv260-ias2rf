// Minimal offline renderer for the HMI .dc.html artboards (sc-for, sc-if, {{holes}}), used only to export PNGs.
(function () {
  window.DCLogic = class { constructor(props) { this.props = props || {}; this.state = {}; } setState(o) { Object.assign(this.state, o); } forceUpdate() {} };
  function look(path, scope) {
    path = path.trim();
    if (path === 'true') return true; if (path === 'false') return false;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), scope);
  }
  function interp(str, scope) {
    const whole = str.match(/^\s*\{\{([^}]+)\}\}\s*$/);
    if (whole) return look(whole[1], scope);
    return str.replace(/\{\{([^}]+)\}\}/g, (_, p) => { const v = look(p, scope); return v == null ? '' : String(v); });
  }
  function expand(node, scope) {
    if (node.nodeType === 3) { if (node.nodeValue.includes('{{')) node.nodeValue = String(interp(node.nodeValue, scope) ?? ''); return; }
    if (node.nodeType !== 1) return;
    const tag = node.localName;
    if (tag === 'sc-for') {
      const list = look(node.getAttribute('list').replace(/[{}]/g, ''), scope) || [];
      const as = node.getAttribute('as');
      const frag = [];
      list.forEach((item, i) => {
        const sc = Object.assign({}, scope, { [as]: item, $index: i });
        for (const ch of Array.from(node.childNodes)) { const c = ch.cloneNode(true); frag.push([c, sc]); }
      });
      for (const [c, sc] of frag) { node.parentNode.insertBefore(c, node); expand(c, sc); }
      node.remove(); return;
    }
    if (tag === 'sc-if') {
      const v = look(node.getAttribute('value').replace(/[{}]/g, ''), scope);
      if (v) { for (const ch of Array.from(node.childNodes)) { node.parentNode.insertBefore(ch, node); expand(ch, scope); } }
      node.remove(); return;
    }
    for (const a of Array.from(node.attributes)) {
      if (!a.value.includes('{{')) continue;
      const v = interp(a.value, scope);
      if (typeof v === 'function' || /^on[A-Z]/.test(a.name)) { node.removeAttribute(a.name); continue; }
      if (typeof v === 'boolean') { if (v) node.setAttribute(a.name, ''); else node.removeAttribute(a.name); continue; }
      node.setAttribute(a.name, v == null ? '' : String(v));
    }
    for (const ch of Array.from(node.childNodes)) expand(ch, scope);
  }
  document.addEventListener('DOMContentLoaded', () => {
    const s = document.querySelector('script[data-dc-script]');
    const Component = new Function('DCLogic', s.textContent + '\nreturn Component;')(window.DCLogic);
    const comp = new Component({});
    const vals = comp.renderVals();
    const root = document.querySelector('x-dc');
    const helmet = root.querySelector('helmet');
    if (helmet) { for (const ch of Array.from(helmet.childNodes)) document.head.appendChild(ch); helmet.remove(); }
    for (const ch of Array.from(root.childNodes)) expand(ch, vals);
    for (const ch of Array.from(root.childNodes)) root.parentNode.insertBefore(ch, root);
    root.remove();
    document.body.style.margin = '0';
  });
})();
