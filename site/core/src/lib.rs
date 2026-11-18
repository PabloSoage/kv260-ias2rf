use std::collections::HashMap;
use std::f32::consts::PI;
use wasm_bindgen::prelude::*;

const GRID_X: usize = 16;
const GRID_Y: usize = 8;
const GRID_Z: usize = 16;

#[derive(Clone)]
struct PartEntry {
    idx: u32,
    id: String,
    ref_lower: String,
    val_lower: String,
    mpn_lower: String,
    desc_lower: String,
    nets: Vec<String>,
    group_id: u8,
    // Base unexploded world AABB in Three.js Y-up metres
    bx0: f32,
    by0: f32,
    bz0: f32,
    bx1: f32,
    by1: f32,
    bz1: f32,
    vol: f32,
    // Active world AABB (after group offset + active mask)
    ax0: f32,
    ay0: f32,
    az0: f32,
    ax1: f32,
    ay1: f32,
    az1: f32,
    visible: bool,
}

#[wasm_bindgen]
pub struct SiteCore {
    parts: Vec<PartEntry>,
    id_to_slot: HashMap<String, usize>,
    net_map: HashMap<String, Vec<u32>>,
    // Uniform 3-D acceleration grid covering current transformed world bounds
    cells: Vec<Vec<u16>>,
    gmin: [f32; 3],
    gmax: [f32; 3],
    inv_cell: [f32; 3],
}

#[wasm_bindgen]
impl SiteCore {
    #[wasm_bindgen(constructor)]
    pub fn new() -> SiteCore {
        SiteCore {
            parts: Vec::with_capacity(900),
            id_to_slot: HashMap::new(),
            net_map: HashMap::new(),
            cells: vec![Vec::new(); GRID_X * GRID_Y * GRID_Z],
            gmin: [-0.2, -0.1, -0.2],
            gmax: [0.2, 0.2, 0.2],
            inv_cell: [40.0, 26.6, 40.0],
        }
    }

    pub fn clear_parts(&mut self) {
        self.parts.clear();
        self.id_to_slot.clear();
        self.net_map.clear();
        for c in &mut self.cells {
            c.clear();
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn add_part(
        &mut self,
        idx: u32,
        id: &str,
        ref_name: &str,
        value: &str,
        mpn: &str,
        desc: &str,
        nets_csv: &str,
        group_id: u8,
        x0: f32,
        y0: f32,
        z0: f32,
        x1: f32,
        y1: f32,
        z1: f32,
    ) {
        let mut nets = Vec::new();
        for raw in nets_csv.split('\n') {
            let n = raw.trim();
            if n.is_empty() {
                continue;
            }
            nets.push(n.to_ascii_lowercase());
            self.net_map.entry(n.to_string()).or_default().push(idx);
        }
        let lx0 = x0.min(x1);
        let lx1 = x0.max(x1).max(lx0 + 0.0005);
        let ly0 = y0.min(y1);
        let ly1 = y0.max(y1).max(ly0 + 0.0006);
        let lz0 = z0.min(z1);
        let lz1 = z0.max(z1).max(lz0 + 0.0005);
        let vol = ((lx1 - lx0) * (ly1 - ly0) * (lz1 - lz0)).max(1e-12);

        let slot = self.parts.len();
        self.id_to_slot.insert(id.to_string(), slot);
        self.parts.push(PartEntry {
            idx,
            id: id.to_string(),
            ref_lower: ref_name.to_ascii_lowercase(),
            val_lower: value.to_ascii_lowercase(),
            mpn_lower: mpn.to_ascii_lowercase(),
            desc_lower: desc.to_ascii_lowercase(),
            nets,
            group_id,
            bx0: lx0,
            by0: ly0,
            bz0: lz0,
            bx1: lx1,
            by1: ly1,
            bz1: lz1,
            vol,
            ax0: lx0,
            ay0: ly0,
            az0: lz0,
            ax1: lx1,
            ay1: ly1,
            az1: lz1,
            visible: true,
        });
    }

    pub fn part_count(&self) -> usize {
        self.parts.len()
    }

    /// Update per-group Y translation offsets (len >= 8) and group visibility bitmask,
    /// then rebuild the 3-D uniform spatial acceleration grid.
    pub fn set_group_transforms(&mut self, y_offsets: &[f32], visible_mask: u32) {
        let mut minp = [f32::INFINITY; 3];
        let mut maxp = [f32::NEG_INFINITY; 3];
        let mut any = false;

        for p in &mut self.parts {
            let gid = p.group_id as usize;
            let vis = (visible_mask & (1u32 << (gid.min(31)))) != 0;
            p.visible = vis;
            if !vis {
                continue;
            }
            let dy = *y_offsets.get(gid).unwrap_or(&0.0);
            p.ax0 = p.bx0;
            p.ax1 = p.bx1;
            p.ay0 = p.by0 + dy;
            p.ay1 = p.by1 + dy;
            p.az0 = p.bz0;
            p.az1 = p.bz1;

            minp[0] = minp[0].min(p.ax0);
            minp[1] = minp[1].min(p.ay0);
            minp[2] = minp[2].min(p.az0);
            maxp[0] = maxp[0].max(p.ax1);
            maxp[1] = maxp[1].max(p.ay1);
            maxp[2] = maxp[2].max(p.az1);
            any = true;
        }

        for c in &mut self.cells {
            c.clear();
        }
        if !any {
            return;
        }

        let pad = 0.002;
        self.gmin = [minp[0] - pad, minp[1] - pad, minp[2] - pad];
        self.gmax = [
            (maxp[0] + pad).max(minp[0] + 0.01),
            (maxp[1] + pad).max(minp[1] + 0.01),
            (maxp[2] + pad).max(minp[2] + 0.01),
        ];
        self.inv_cell = [
            GRID_X as f32 / (self.gmax[0] - self.gmin[0]),
            GRID_Y as f32 / (self.gmax[1] - self.gmin[1]),
            GRID_Z as f32 / (self.gmax[2] - self.gmin[2]),
        ];

        for (slot, p) in self.parts.iter().enumerate() {
            if !p.visible {
                continue;
            }
            let ix0 = (((p.ax0 - self.gmin[0]) * self.inv_cell[0]).floor() as isize).clamp(0, GRID_X as isize - 1) as usize;
            let ix1 = (((p.ax1 - self.gmin[0]) * self.inv_cell[0]).floor() as isize).clamp(0, GRID_X as isize - 1) as usize;
            let iy0 = (((p.ay0 - self.gmin[1]) * self.inv_cell[1]).floor() as isize).clamp(0, GRID_Y as isize - 1) as usize;
            let iy1 = (((p.ay1 - self.gmin[1]) * self.inv_cell[1]).floor() as isize).clamp(0, GRID_Y as isize - 1) as usize;
            let iz0 = (((p.az0 - self.gmin[2]) * self.inv_cell[2]).floor() as isize).clamp(0, GRID_Z as isize - 1) as usize;
            let iz1 = (((p.az1 - self.gmin[2]) * self.inv_cell[2]).floor() as isize).clamp(0, GRID_Z as isize - 1) as usize;

            let s_u16 = slot as u16;
            for iz in iz0..=iz1 {
                for iy in iy0..=iy1 {
                    let row = (iz * GRID_Y + iy) * GRID_X;
                    for ix in ix0..=ix1 {
                        self.cells[row + ix].push(s_u16);
                    }
                }
            }
        }
    }

    /// Ray-grid DDA intersect against transformed part AABBs.
    /// Returns component idx or -1 if no hit.
    pub fn pick_ray(&self, ox: f32, oy: f32, oz: f32, dx: f32, dy: f32, dz: f32) -> i32 {
        let len = (dx * dx + dy * dy + dz * dz).sqrt();
        if len < 1e-9 {
            return -1;
        }
        let dir = [dx / len, dy / len, dz / len];
        let orig = [ox, oy, oz];

        let (gt0, gt1) = match intersect_aabb(orig, dir, self.gmin, self.gmax) {
            Some(v) => v,
            None => return -1,
        };
        let t_start = gt0.max(0.0);
        if gt1 < t_start {
            return -1;
        }

        let cell_w = [
            (self.gmax[0] - self.gmin[0]) / GRID_X as f32,
            (self.gmax[1] - self.gmin[1]) / GRID_Y as f32,
            (self.gmax[2] - self.gmin[2]) / GRID_Z as f32,
        ];
        let p0 = [
            orig[0] + dir[0] * (t_start + 1e-5),
            orig[1] + dir[1] * (t_start + 1e-5),
            orig[2] + dir[2] * (t_start + 1e-5),
        ];

        let mut ix = (((p0[0] - self.gmin[0]) * self.inv_cell[0]).floor() as isize).clamp(0, GRID_X as isize - 1);
        let mut iy = (((p0[1] - self.gmin[1]) * self.inv_cell[1]).floor() as isize).clamp(0, GRID_Y as isize - 1);
        let mut iz = (((p0[2] - self.gmin[2]) * self.inv_cell[2]).floor() as isize).clamp(0, GRID_Z as isize - 1);

        let step_x: isize = if dir[0] >= 0.0 { 1 } else { -1 };
        let step_y: isize = if dir[1] >= 0.0 { 1 } else { -1 };
        let step_z: isize = if dir[2] >= 0.0 { 1 } else { -1 };

        let next_b = |i: isize, step: isize, minv: f32, cw: f32| -> f32 {
            let b_idx = if step > 0 { i + 1 } else { i };
            minv + b_idx as f32 * cw
        };

        let mut t_max_x = if dir[0].abs() > 1e-8 { (next_b(ix, step_x, self.gmin[0], cell_w[0]) - orig[0]) / dir[0] } else { f32::INFINITY };
        let mut t_max_y = if dir[1].abs() > 1e-8 { (next_b(iy, step_y, self.gmin[1], cell_w[1]) - orig[1]) / dir[1] } else { f32::INFINITY };
        let mut t_max_z = if dir[2].abs() > 1e-8 { (next_b(iz, step_z, self.gmin[2], cell_w[2]) - orig[2]) / dir[2] } else { f32::INFINITY };

        let t_delta_x = if dir[0].abs() > 1e-8 { cell_w[0] / dir[0].abs() } else { f32::INFINITY };
        let t_delta_y = if dir[1].abs() > 1e-8 { cell_w[1] / dir[1].abs() } else { f32::INFINITY };
        let t_delta_z = if dir[2].abs() > 1e-8 { cell_w[2] / dir[2].abs() } else { f32::INFINITY };

        let mut best_t = f32::INFINITY;
        let mut best_vol = f32::INFINITY;
        let mut best_idx: i32 = -1;
        let mut cur_t = t_start;

        // Deduplicate per cell traversal cleanly without allocating every ray
        for _ in 0..64 {
            if ix < 0 || ix >= GRID_X as isize || iy < 0 || iy >= GRID_Y as isize || iz < 0 || iz >= GRID_Z as isize {
                break;
            }
            // Early exit once voxel entry exceeds best_t + 2.5 mm depth window
            if cur_t > best_t + 0.0025 {
                break;
            }
            let cidx = ((iz as usize) * GRID_Y + (iy as usize)) * GRID_X + (ix as usize);
            for &slot in &self.cells[cidx] {
                let p = &self.parts[slot as usize];
                if !p.visible {
                    continue;
                }
                if let Some((ht0, _)) = intersect_aabb(orig, dir, [p.ax0, p.ay0, p.az0], [p.ax1, p.ay1, p.az1]) {
                    if ht0 <= best_t + 0.0025 {
                        // Prefer frontmost object; inside a 2.5 mm cluster prefer tighter package over big carrier slabs
                        let near_tie = (ht0 - best_t).abs() <= 0.0022;
                        if ht0 + 0.0022 < best_t || (near_tie && p.vol < best_vol) || best_idx < 0 {
                            best_t = best_t.min(ht0);
                            best_vol = if (ht0 - best_t).abs() <= 0.0022 { best_vol.min(p.vol) } else { p.vol };
                            best_idx = p.idx as i32;
                        }
                    }
                }
            }

            if t_max_x <= t_max_y && t_max_x <= t_max_z {
                cur_t = t_max_x;
                t_max_x += t_delta_x;
                ix += step_x;
            } else if t_max_y <= t_max_z {
                cur_t = t_max_y;
                t_max_y += t_delta_y;
                iy += step_y;
            } else {
                cur_t = t_max_z;
                t_max_z += t_delta_z;
                iz += step_z;
            }
        }
        best_idx
    }

    pub fn bench_pick_rays(&self, iterations: u32) -> i32 {
        let mut acc = 0i32;
        for k in 0..iterations {
            let fx = -0.09 + 0.21 * ((k % 47) as f32 / 46.0);
            let fz = -0.11 + 0.14 * (((k / 47) % 37) as f32 / 36.0);
            let hit = self.pick_ray(fx, 0.22, fz, 0.02, -1.0, -0.05);
            acc = acc.wrapping_add(hit);
        }
        acc
    }

    /// Scored search returning JSON array of top matching component indices `[u32, ...]`.
    pub fn search(&self, query: &str, max_results: usize) -> String {
        let q = query.trim().to_ascii_lowercase();
        if q.is_empty() {
            return "[]".to_string();
        }
        let mut scored: Vec<(u8, u32)> = Vec::new();
        for p in &self.parts {
            let mut rank = 255u8;
            if p.ref_lower == q || p.id.eq_ignore_ascii_case(&q) {
                rank = 0;
            } else if p.ref_lower.starts_with(&q) {
                rank = 1;
            } else if p.val_lower.contains(&q) || p.mpn_lower.contains(&q) {
                rank = 2;
            } else if p.nets.iter().any(|n| n.contains(&q)) {
                rank = 3;
            } else if p.desc_lower.contains(&q) || p.ref_lower.contains(&q) {
                rank = 4;
            }
            if rank < 255 {
                scored.push((rank, p.idx));
            }
        }
        scored.sort_unstable_by_key(|a| (a.0, a.1));
        scored.truncate(max_results);

        let mut out = String::from("[");
        for (i, &(_, idx)) in scored.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&idx.to_string());
        }
        out.push(']');
        out
    }

    pub fn net_mates(&self, net: &str) -> Vec<u32> {
        self.net_map.get(net).cloned().unwrap_or_default()
    }

    /// DSP Signal-Chain Simulation for Mock-up #1 (all 8 RF/radar modes).
    /// Output layout: 64 time-domain samples, 64 FFT dBFS bins (-90..0), 5 stage levels (dBm).
    pub fn sim_dsp_tick(&self, mode: u8, time_s: f32, snr_db: f32) -> Vec<f32> {
        let mut out = vec![0.0f32; 64 + 64 + 5];
        let noise_amp = 10f32.powf(-snr_db / 20.0);

        for i in 0..64 {
            let ph = i as f32 / 64.0;
            let n = ((i as f32 * 19.3 + time_s * 37.0).sin()) * noise_amp;
            let sig = match mode {
                0 => 0.72 * (2.0 * PI * (3.0 * ph + time_s * 1.4)).sin() + 0.18 * (2.0 * PI * (19.0 * ph + time_s * 3.0)).sin(),
                1 => 0.55 * (1.0 + 0.65 * (2.0 * PI * (ph * 2.0 + time_s * 2.0)).sin()) * (2.0 * PI * (12.0 * ph + time_s * 2.5)).cos(),
                2 => 0.50 * (1.0 + 0.75 * (2.0 * PI * (ph + time_s * 1.6)).sin()) * (2.0 * PI * (8.0 * ph + time_s * 1.8)).cos(),
                3 => 0.78 * (2.0 * PI * (6.0 * ph + time_s * 2.2)).sin() * (2.0 * PI * (ph * 1.5 + time_s)).cos(),
                4 => 0.80 * (2.0 * PI * (10.0 * ph + time_s * 2.0 + 1.8 * (2.0 * PI * ph).sin())).sin(),
                5 => {
                    // Mode-S 1090 MHz Manchester PPM pulses
                    let bit = ((i + (time_s * 18.0) as usize) / 4) % 16;
                    if matches!(bit, 0 | 2 | 7 | 9 | 12) { 0.88 } else { 0.04 }
                }
                6 => {
                    // FMCW de-chirped beat + range targets
                    let beat1 = 0.68 * (2.0 * PI * (7.0 * ph + time_s * 1.5)).cos();
                    let beat2 = 0.42 * (2.0 * PI * (18.0 * ph - time_s * 1.1)).cos();
                    beat1 + beat2
                }
                _ => 0.65 * (2.0 * PI * (9.0 * ph + time_s * 2.0)).sin() + 0.35 * (2.0 * PI * (11.0 * ph + time_s * 2.0)).sin(),
            };
            out[i] = (sig + n).clamp(-1.0, 1.0);
        }

        // Compute DFT magnitude in dBFS across 64 bins
        for k in 0..64 {
            let mut re = 0.0f32;
            let mut im = 0.0f32;
            for i in 0..64 {
                let ang = -2.0 * PI * (k as f32) * (i as f32) / 64.0;
                re += out[i] * ang.cos();
                im += out[i] * ang.sin();
            }
            let mag = ((re * re + im * im).sqrt() / 32.0).max(1e-4);
            out[64 + k] = (20.0 * mag.log10()).clamp(-80.0, 0.0);
        }

        let base_pwr = match mode {
            6 => [-62.0, -41.0, -18.0, -3.5, -1.0],
            7 => [-24.0, -14.0, -6.0, 4.0, 13.0],
            _ => [-78.0, -54.0, -28.0, -12.0, -4.0],
        };
        for j in 0..5 {
            out[128 + j] = base_pwr[j] + (time_s * 2.0 + j as f32).sin() * 0.6;
        }
        out
    }

    /// Stateful LVDS 512-tap IDELAYE3 & SGMII Failover FSM Simulation for Mock-up #2.
    /// Returns `[state_code, locked_tap, eye_open_ps, dwell_pct, dl_up, ul_up, eth_healthy, crc_errs, 64 eye samples]`.
    pub fn sim_lvds_tick(&self, skew_ps: f32, fsm_mode: u8, step: u32) -> Vec<f32> {
        let mut out = vec![0.0f32; 8 + 64];
        let phase = (step % 180) as f32 / 180.0;
        let center_tap = (256.0 + skew_ps * 0.36).clamp(40.0, 470.0);
        let half_open = (172.0 - skew_ps * 0.46).max(24.0);
        let eye_ps = ((2.0 * half_open / 511.0) * 1000.0).round();

        let (st, dl_up, ul_up, eth_ok, crc, dwell) = match fsm_mode {
            1 => (1.0, 1.0, 1.0, 0.0, 0.0, 100.0), // POL_MIRROR_1P1 (ETH cut failover)
            2 => {
                // Retrain cycle every 180 steps
                if step % 180 < 55 {
                    (2.0, 0.0, 0.0, 1.0, 1.0, (step % 55) as f32 * 100.0 / 55.0)
                } else {
                    (0.0, 1.0, 1.0, 1.0, 0.0, 100.0)
                }
            }
            3 => (3.0, 1.0, 1.0, 1.0, 0.0, 100.0), // Si549 400 MHz switch
            _ => (0.0, 1.0, 1.0, 1.0, 0.0, 100.0), // POL_SPLIT locked
        };

        out[0] = st;
        out[1] = if st == 2.0 { (phase * 511.0).round() } else { center_tap.round() };
        out[2] = eye_ps;
        out[3] = dwell;
        out[4] = dl_up;
        out[5] = ul_up;
        out[6] = eth_ok;
        out[7] = crc;

        for i in 0..64 {
            let tap = (i as f32 / 63.0) * 511.0;
            let dist = (tap - center_tap).abs();
            let opening = ((half_open * 0.88 - dist) / 38.0).clamp(-1.0, 1.0);
            let jitter = ((step as f32 * 0.35 + i as f32 * 2.1).sin()) * 0.07;
            out[8 + i] = (-opening + jitter).clamp(-1.0, 1.0);
        }
        out
    }

    /// R5F OCM Mailbox (0x3EE0_0000) & Hardware TX_KEY (0x8000_0038) Interlock for Mock-up #3.
    pub fn sim_mailbox_tick(
        &self,
        speed_kmh: f32,
        ptt_sec: f32,
        lic_ok: bool,
        ptt_req: bool,
        gps_ok: bool,
        step: u32,
    ) -> Vec<u32> {
        let parked = speed_kmh <= 0.05;
        let tot_ok = ptt_sec <= 180.0;
        let unlocked = parked && lic_ok && ptt_req && tot_ok;
        let reason = if !parked {
            1
        } else if !lic_ok {
            2
        } else if !ptt_req {
            3
        } else if !tot_ok {
            4
        } else {
            0
        };
        let tx_key = if unlocked { 0x4B45_5901 } else { 0x0000_0000 };
        let dsp_ctrl = if unlocked { 0x0000_0003 } else { 0x0000_0001 };
        let jitter_ns = if gps_ok { 28 + (step * 7) % 14 } else { 7300 };

        vec![
            0x4B52_4941, // magic "KRIA"
            1040 + step,
            speed_kmh.round() as u32,
            jitter_ns,
            tx_key,
            dsp_ctrl,
            reason,
        ]
    }

    /// Mirror-Safe J9<->J1502 NOR gate + Montero V80 CAN 2.0 Differential Bit Waveform for Mock-up #4.
    pub fn sim_can_tick(&self, ffc_type_d: bool, can_tx_dom: bool, frame_idx: u8, step: u32) -> Vec<f32> {
        let mut out = vec![0.0f32; 4 + 96];
        let pps_j9_pin = if ffc_type_d { 4.0 } else { 12.0 };
        let can_tx_pin = if ffc_type_d { 10.0 } else { 6.0 };
        let txd_low = can_tx_dom;
        out[0] = pps_j9_pin;
        out[1] = can_tx_pin;
        out[2] = if txd_low { 1.0 } else { 0.0 };
        out[3] = frame_idx as f32;

        // Deterministic 11-bit CAN frame pattern per ID + scrolling bit offset
        let seed: u64 = match frame_idx {
            0 => 0x2150_1A90_1A88_0040,
            1 => 0x2180_0BB8_5C00_0012,
            2 => 0x2360_01F4_0010_0000,
            _ => 0x4120_038A_2000_0201,
        };
        let shift = (step / 2) % 64;
        for i in 0..96 {
            let bit_idx = ((i / 2) as u64 + shift as u64) % 64;
            let bit = if can_tx_dom { ((seed >> bit_idx) & 1) == 1 } else { false };
            // Differential half-swing relative to 2.5V common-mode (encoded as 0.0 recessive, +1.0 dominant)
            out[4 + i] = if bit { 1.0 } else { 0.0 };
        }
        out
    }
}

impl Default for SiteCore {
    fn default() -> Self {
        Self::new()
    }
}

#[inline]
fn intersect_aabb(o: [f32; 3], d: [f32; 3], bmin: [f32; 3], bmax: [f32; 3]) -> Option<(f32, f32)> {
    let mut tmin = f32::NEG_INFINITY;
    let mut tmax = f32::INFINITY;
    for k in 0..3 {
        if d[k].abs() < 1e-8 {
            if o[k] < bmin[k] || o[k] > bmax[k] {
                return None;
            }
        } else {
            let inv = 1.0 / d[k];
            let mut t1 = (bmin[k] - o[k]) * inv;
            let mut t2 = (bmax[k] - o[k]) * inv;
            if t1 > t2 {
                std::mem::swap(&mut t1, &mut t2);
            }
            tmin = tmin.max(t1);
            tmax = tmax.min(t2);
            if tmin > tmax {
                return None;
            }
        }
    }
    if tmax < 0.0 {
        None
    } else {
        Some((tmin, tmax))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spatial_grid_prefers_component_over_carrier() {
        let mut core = SiteCore::new();
        core.add_part(0, "KV260_CARRIER", "KV260", "Carrier", "", "Carrier card", "", 1, -0.01, -0.002, -0.109, 0.13, 0.0, 0.01);
        core.add_part(1, "U1506", "U1506", "TCAN330DCNT", "TCAN330DCNT", "Vehicle CAN transceiver", "CAN_H\nCAN_L\n+3V3_D", 0, -0.014, 0.0005, -0.010, -0.011, 0.0018, -0.006);
        let y = [0.0f32; 8];
        core.set_group_transforms(&y, 0xff);

        // Downward ray onto U1506
        let hit = core.pick_ray(-0.0125, 0.05, -0.008, 0.0, -1.0, 0.0);
        assert_eq!(hit, 1);

        // Search and net lookup
        assert_eq!(core.search("U1506", 5), "[1]");
        assert_eq!(core.net_mates("CAN_H"), vec![1]);
    }

    #[test]
    fn simulations_produce_expected_interlock_and_waveforms() {
        let core = SiteCore::new();
        let locked = core.sim_mailbox_tick(68.0, 10.0, true, true, true, 1);
        assert_eq!(locked[4], 0);
        assert_eq!(locked[6], 1);

        let unlocked = core.sim_mailbox_tick(0.0, 10.0, true, true, true, 2);
        assert_eq!(unlocked[4], 0x4B45_5901);
        assert_eq!(unlocked[6], 0);

        let dsp = core.sim_dsp_tick(6, 0.5, 45.0);
        assert_eq!(dsp.len(), 64 + 64 + 5);
        let lvds = core.sim_lvds_tick(42.0, 0, 10);
        assert_eq!(lvds.len(), 8 + 64);
        let can = core.sim_can_tick(true, true, 0, 5);
        assert_eq!(can.len(), 4 + 96);
        assert_eq!(can[0], 4.0);
        assert_eq!(can[1], 10.0);
    }
}
