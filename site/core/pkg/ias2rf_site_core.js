export class SiteCore {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        SiteCoreFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_sitecore_free(ptr, 0);
    }
    /**
     * @param {number} idx
     * @param {string} id
     * @param {string} ref_name
     * @param {string} value
     * @param {string} mpn
     * @param {string} desc
     * @param {string} nets_csv
     * @param {number} group_id
     * @param {number} x0
     * @param {number} y0
     * @param {number} z0
     * @param {number} x1
     * @param {number} y1
     * @param {number} z1
     */
    add_part(idx, id, ref_name, value, mpn, desc, nets_csv, group_id, x0, y0, z0, x1, y1, z1) {
        const val7 = +idx;
        const val8 = +group_id;
        const val9 = +x0;
        const val10 = +y0;
        const val11 = +z0;
        const val12 = +x1;
        const val13 = +y1;
        const val14 = +z1;
        let ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, ptr4, len4, ptr5, len5;
        try {
            ptr0 = passStringToWasm0(id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len0 = WASM_VECTOR_LEN;
            ptr1 = passStringToWasm0(ref_name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len1 = WASM_VECTOR_LEN;
            ptr2 = passStringToWasm0(value, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len2 = WASM_VECTOR_LEN;
            ptr3 = passStringToWasm0(mpn, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len3 = WASM_VECTOR_LEN;
            ptr4 = passStringToWasm0(desc, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len4 = WASM_VECTOR_LEN;
            ptr5 = passStringToWasm0(nets_csv, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            len5 = WASM_VECTOR_LEN;
        } catch (e) {
            if (ptr5) { wasm.__wbindgen_free(ptr5, len5 * 1, 1); }
            if (ptr4) { wasm.__wbindgen_free(ptr4, len4 * 1, 1); }
            if (ptr3) { wasm.__wbindgen_free(ptr3, len3 * 1, 1); }
            if (ptr2) { wasm.__wbindgen_free(ptr2, len2 * 1, 1); }
            if (ptr1) { wasm.__wbindgen_free(ptr1, len1 * 1, 1); }
            if (ptr0) { wasm.__wbindgen_free(ptr0, len0 * 1, 1); }
            throw e;
        }
        wasm.sitecore_add_part(this.__wbg_ptr, val7, ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, ptr4, len4, ptr5, len5, val8, val9, val10, val11, val12, val13, val14);
    }
    /**
     * @param {number} iterations
     * @returns {number}
     */
    bench_pick_rays(iterations) {
        const ret = wasm.sitecore_bench_pick_rays(this.__wbg_ptr, iterations);
        return ret;
    }
    clear_parts() {
        wasm.sitecore_clear_parts(this.__wbg_ptr);
    }
    /**
     * @param {string} net
     * @returns {Uint32Array}
     */
    net_mates(net) {
        const ptr0 = passStringToWasm0(net, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.sitecore_net_mates(this.__wbg_ptr, ptr0, len0);
        var v2 = getArrayU32FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v2;
    }
    constructor() {
        const ret = wasm.sitecore_new();
        this.__wbg_ptr = ret;
        SiteCoreFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * @returns {number}
     */
    part_count() {
        const ret = wasm.sitecore_part_count(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * Ray-grid DDA intersect against transformed part AABBs.
     * Returns component idx or -1 if no hit.
     * @param {number} ox
     * @param {number} oy
     * @param {number} oz
     * @param {number} dx
     * @param {number} dy
     * @param {number} dz
     * @returns {number}
     */
    pick_ray(ox, oy, oz, dx, dy, dz) {
        const ret = wasm.sitecore_pick_ray(this.__wbg_ptr, ox, oy, oz, dx, dy, dz);
        return ret;
    }
    /**
     * Scored search returning JSON array of top matching component indices `[u32, ...]`.
     * @param {string} query
     * @param {number} max_results
     * @returns {string}
     */
    search(query, max_results) {
        let deferred3_0;
        let deferred3_1;
        try {
            const val2 = +max_results;
            const ptr0 = passStringToWasm0(query, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ret = wasm.sitecore_search(this.__wbg_ptr, ptr0, len0, val2);
            deferred3_0 = ret[0];
            deferred3_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
        }
    }
    /**
     * Update per-group Y translation offsets (len >= 8) and group visibility bitmask,
     * then rebuild the 3-D uniform spatial acceleration grid.
     * @param {Float32Array | number[]} y_offsets
     * @param {number} visible_mask
     */
    set_group_transforms(y_offsets, visible_mask) {
        const val2 = +visible_mask;
        const ptr0 = passArrayF32ToWasm0(y_offsets, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        wasm.sitecore_set_group_transforms(this.__wbg_ptr, ptr0, len0, val2);
    }
    /**
     * @param {number} idx
     * @param {number} side_mask
     * @param {number} x0
     * @param {number} y0
     * @param {number} z0
     * @param {number} x1
     * @param {number} y1
     * @param {number} z1
     */
    set_part_bounds(idx, side_mask, x0, y0, z0, x1, y1, z1) {
        wasm.sitecore_set_part_bounds(this.__wbg_ptr, idx, side_mask, x0, y0, z0, x1, y1, z1);
    }
    /**
     * Mirror-Safe J9<->J1502 NOR gate + Montero V80 CAN 2.0 Differential Bit Waveform for Mock-up #4.
     * @param {boolean} ffc_type_d
     * @param {boolean} can_tx_dom
     * @param {number} frame_idx
     * @param {number} step
     * @returns {Float32Array}
     */
    sim_can_tick(ffc_type_d, can_tx_dom, frame_idx, step) {
        const ret = wasm.sitecore_sim_can_tick(this.__wbg_ptr, ffc_type_d, can_tx_dom, frame_idx, step);
        var v1 = getArrayF32FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
    /**
     * DSP Signal-Chain Simulation for Mock-up #1 (all 8 RF/radar modes).
     * Output layout: 64 time-domain samples, 64 FFT dBFS bins (-90..0), 5 stage levels (dBm).
     * @param {number} mode
     * @param {number} time_s
     * @param {number} snr_db
     * @returns {Float32Array}
     */
    sim_dsp_tick(mode, time_s, snr_db) {
        const ret = wasm.sitecore_sim_dsp_tick(this.__wbg_ptr, mode, time_s, snr_db);
        var v1 = getArrayF32FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
    /**
     * Stateful LVDS 512-tap IDELAYE3 & SGMII Failover FSM Simulation for Mock-up #2.
     * Returns `[state_code, locked_tap, eye_open_ps, dwell_pct, dl_up, ul_up, eth_healthy, crc_errs, 64 eye samples]`.
     * @param {number} skew_ps
     * @param {number} fsm_mode
     * @param {number} step
     * @returns {Float32Array}
     */
    sim_lvds_tick(skew_ps, fsm_mode, step) {
        const ret = wasm.sitecore_sim_lvds_tick(this.__wbg_ptr, skew_ps, fsm_mode, step);
        var v1 = getArrayF32FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
    /**
     * R5F OCM Mailbox (0x3EE0_0000) & Hardware TX_KEY (0x8000_0038) Interlock for Mock-up #3.
     * @param {number} speed_kmh
     * @param {number} ptt_sec
     * @param {boolean} lic_ok
     * @param {boolean} ptt_req
     * @param {boolean} gps_ok
     * @param {number} step
     * @returns {Uint32Array}
     */
    sim_mailbox_tick(speed_kmh, ptt_sec, lic_ok, ptt_req, gps_ok, step) {
        const ret = wasm.sitecore_sim_mailbox_tick(this.__wbg_ptr, speed_kmh, ptt_sec, lic_ok, ptt_req, gps_ok, step);
        var v1 = getArrayU32FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
}
if (Symbol.dispose) SiteCore.prototype[Symbol.dispose] = SiteCore.prototype.free;
function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg___wbindgen_throw_4c88d8bf264fd984: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbindgen_init_externref_table: function() {
            const table = wasm.__wbindgen_externrefs;
            table.set(0, undefined);
            table.set(1024, undefined);
            table.set(1025, null);
            table.set(1026, true);
            table.set(1027, false);
        },
    };
    return {
        __proto__: null,
        "./ias2rf_site_core_bg.js": import0,
    };
}

const SiteCoreFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_sitecore_free(ptr, 1));

function getArrayF32FromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return getFloat32ArrayMemory0().subarray(ptr / 4, ptr / 4 + len);
}

function getArrayU32FromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return getUint32ArrayMemory0().subarray(ptr / 4, ptr / 4 + len);
}

let cachedFloat32ArrayMemory0 = null;
function getFloat32ArrayMemory0() {
    if (cachedFloat32ArrayMemory0 === null || cachedFloat32ArrayMemory0.byteLength === 0) {
        cachedFloat32ArrayMemory0 = new Float32Array(wasm.memory.buffer);
    }
    return cachedFloat32ArrayMemory0;
}

function getStringFromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return decodeText(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

let cachedUint32ArrayMemory0 = null;
function getUint32ArrayMemory0() {
    if (cachedUint32ArrayMemory0 === null || cachedUint32ArrayMemory0.byteLength === 0) {
        cachedUint32ArrayMemory0 = new Uint32Array(wasm.memory.buffer);
    }
    return cachedUint32ArrayMemory0;
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function passArrayF32ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 4, 4) >>> 0;
    getFloat32ArrayMemory0().set(arg, ptr / 4);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (realloc === undefined) {
        const buf = cachedTextEncoder.encode(arg);
        const ptr = malloc(buf.length, 1) >>> 0;
        getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf);
        WASM_VECTOR_LEN = buf.length;
        return ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(bytes) {
    numBytesDecoded += bytes.length;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true });
        cachedTextDecoder.decode();
        numBytesDecoded = bytes.length;
    }
    return cachedTextDecoder.decode(bytes);
}

const cachedTextEncoder = new TextEncoder();

if (!('encodeInto' in cachedTextEncoder)) {
    cachedTextEncoder.encodeInto = function (arg, view) {
        const buf = cachedTextEncoder.encode(arg);
        view.set(buf);
        return {
            read: arg.length,
            written: buf.length
        };
    };
}

let WASM_VECTOR_LEN = 0;

let wasmModule, wasmInstance, wasm;
function __wbg_finalize_init(instance, module) {
    wasmInstance = instance;
    wasm = instance.exports;
    wasmModule = module;
    cachedFloat32ArrayMemory0 = null;
    cachedUint32ArrayMemory0 = null;
    cachedUint8ArrayMemory0 = null;
    wasm.__wbindgen_start();
    return wasm;
}

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (!module.ok) {
            throw new Error(`failed to fetch Wasm: ${module.status} ${module.statusText} fetching '${module.url}'`);
        }

        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = expectedResponseType(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else { throw e; }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }

    function expectedResponseType(type) {
        switch (type) {
            case 'basic': case 'cors': case 'default': return true;
        }
        return false;
    }
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (module !== undefined) {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

let __wbg_init_promise;
async function __wbg_init(module_or_path) {
    if (wasm !== undefined) return wasm;
    if (__wbg_init_promise === undefined) {
        __wbg_init_promise = __wbg_init_once(module_or_path);
        __wbg_init_promise.catch(() => { __wbg_init_promise = undefined; });
    }
    return __wbg_init_promise;
}

async function __wbg_init_once(module_or_path) {

    if (module_or_path !== undefined) {
        if (Object.getPrototypeOf(module_or_path) === Object.prototype) {
            ({module_or_path} = module_or_path)
        } else {
            console.warn('using deprecated parameters for the initialization function; pass a single object instead')
        }
    }

    if (module_or_path === undefined) {
        module_or_path = new URL('ias2rf_site_core_bg.wasm', import.meta.url);
    }
    const imports = __wbg_get_imports();

    if (typeof module_or_path === 'string' || (typeof Request === 'function' && module_or_path instanceof Request) || (typeof URL === 'function' && module_or_path instanceof URL)) {
        module_or_path = fetch(module_or_path);
    }

    const { instance, module } = await __wbg_load(await module_or_path, imports);

    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };
