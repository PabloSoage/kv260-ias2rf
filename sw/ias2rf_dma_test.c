// SPDX-License-Identifier: BSD-2-Clause
// Userspace Linux smoke-test for KV260 IAS1 PL link (CSRs + AXI DMA S2MM/MM2S)
// Cross-compile on host or build natively on Kria Ubuntu/PetaLinux:
//   aarch64-linux-gnu-gcc -O2 -Wall -o ias2rf_dma_test ias2rf_dma_test.c

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LINK_CSR_BASE       0x80000000ULL
#define LINK_CSR_SPAN       0x10000UL
#define AXI_DMA_BASE        0x80010000ULL
#define AXI_DMA_SPAN        0x10000UL

/* kria_pl_link CSR offsets (LINK_PROTOCOL.md Section 7.2 + 0x34 TX_AXIS_SID) */
#define REG_LINK_CTRL       0x00
#define REG_LINK_STATUS     0x04
#define REG_IDELAY_L0       0x08
#define REG_IDELAY_L1       0x0C
#define REG_ERR_SH_L0       0x10
#define REG_ERR_SH_L1       0x14
#define REG_ERR_CRC         0x18
#define REG_PKT_CNT_RX      0x1C
#define REG_PKT_CNT_DROP    0x20
#define REG_DESKEW_STATUS   0x24
#define REG_PRBS_ERR_CNT    0x28
#define REG_EYE_SCAN_L0     0x2C
#define REG_EYE_SCAN_L1     0x30
#define REG_TX_AXIS_SID     0x34

/* Xilinx AXI DMA Direct Register Mode offsets (PG021) */
#define DMA_MM2S_CR         0x00
#define DMA_MM2S_SR         0x04
#define DMA_MM2S_SA         0x18
#define DMA_MM2S_SA_MSB     0x1C
#define DMA_MM2S_LENGTH     0x28
#define DMA_S2MM_CR         0x30
#define DMA_S2MM_SR         0x34
#define DMA_S2MM_DA         0x48
#define DMA_S2MM_DA_MSB     0x4C
#define DMA_S2MM_LENGTH     0x58

#define DMA_CR_RS           (1u << 0)
#define DMA_CR_RESET        (1u << 2)
#define DMA_SR_HALTED       (1u << 0)
#define DMA_SR_IDLE         (1u << 1)
#define DMA_SR_IOC_IRQ      (1u << 12)
#define DMA_SR_ERR_IRQ      (1u << 14)

static inline uint32_t reg_rd(volatile uint32_t *base, uint32_t off)
{
    return base[off >> 2];
}

static inline void reg_wr(volatile uint32_t *base, uint32_t off, uint32_t val)
{
    base[off >> 2] = val;
}

static void *map_phys(int fd, off_t phys, size_t len)
{
    void *p = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, phys);
    if (p == MAP_FAILED) {
        fprintf(stderr, "mmap(0x%llx) failed: %s\n",
                (unsigned long long)phys, strerror(errno));
        return NULL;
    }
    return p;
}

static int read_sysfs_u64(const char *path, uint64_t *val)
{
    FILE *f = fopen(path, "r");
    if (!f)
        return -1;
    int ok = (fscanf(f, "%lli", (long long *)val) == 1);
    fclose(f);
    return ok ? 0 : -1;
}

static void dump_csrs(volatile uint32_t *csr)
{
    uint32_t st = reg_rd(csr, REG_LINK_STATUS);
    printf("=== IAS1 Link CSRs (0x%08llx) ===\n", LINK_CSR_BASE);
    if (st == 0xDEAD0000U + 0xC10CU) {
        printf("  WARNING: watchdog returned 0xDEAD_C10C (rx_clkdiv stopped / no Artix clock)\n");
        return;
    }
    printf("  LINK_CTRL     = 0x%08x\n", reg_rd(csr, REG_LINK_CTRL));
    printf("  LINK_STATUS   = 0x%08x (state=%u l0=%u l1=%u dsk=%u up=%u idc=%u rem=0x%02x)\n",
           st, st & 7u, (st >> 3) & 1u, (st >> 4) & 1u, (st >> 5) & 1u,
           (st >> 6) & 1u, (st >> 7) & 1u, (st >> 16) & 0xFFu);
    printf("  IDELAY_L0/L1  = 0x%08x / 0x%08x\n",
           reg_rd(csr, REG_IDELAY_L0), reg_rd(csr, REG_IDELAY_L1));
    printf("  ERR_SH_L0/L1  = %u / %u\n",
           reg_rd(csr, REG_ERR_SH_L0), reg_rd(csr, REG_ERR_SH_L1));
    printf("  ERR_CRC       = %u\n", reg_rd(csr, REG_ERR_CRC));
    printf("  PKT_CNT_RX    = %u\n", reg_rd(csr, REG_PKT_CNT_RX));
    printf("  PKT_CNT_DROP  = 0x%08x\n", reg_rd(csr, REG_PKT_CNT_DROP));
    printf("  DESKEW_STATUS = 0x%08x\n", reg_rd(csr, REG_DESKEW_STATUS));
    printf("  PRBS_ERR_CNT  = %u\n", reg_rd(csr, REG_PRBS_ERR_CNT));
    printf("  EYE_L0 / L1   = [%u..%u] / [%u..%u]\n",
           reg_rd(csr, REG_EYE_SCAN_L0) & 0x1FFu, (reg_rd(csr, REG_EYE_SCAN_L0) >> 16) & 0x1FFu,
           reg_rd(csr, REG_EYE_SCAN_L1) & 0x1FFu, (reg_rd(csr, REG_EYE_SCAN_L1) >> 16) & 0x1FFu);
    printf("  TX_AXIS_SID   = 0x%02x\n", reg_rd(csr, REG_TX_AXIS_SID) & 0xFFu);
}

static int dma_reset(volatile uint32_t *dma)
{
    reg_wr(dma, DMA_S2MM_CR, DMA_CR_RESET);
    reg_wr(dma, DMA_MM2S_CR, DMA_CR_RESET);
    for (int i = 0; i < 10000; i++) {
        if (!((reg_rd(dma, DMA_S2MM_CR) | reg_rd(dma, DMA_MM2S_CR)) & DMA_CR_RESET))
            return 0;
        usleep(1);
    }
    fprintf(stderr, "AXI DMA reset timeout\n");
    return -1;
}

static int run_s2mm_capture(volatile uint32_t *dma, uint64_t phys_buf,
                            volatile uint64_t *virt_buf, uint32_t bytes)
{
    if (dma_reset(dma) != 0)
        return -1;

    reg_wr(dma, DMA_S2MM_CR, DMA_CR_RS);
    reg_wr(dma, DMA_S2MM_DA, (uint32_t)(phys_buf & 0xFFFFFFFFULL));
    reg_wr(dma, DMA_S2MM_DA_MSB, (uint32_t)(phys_buf >> 32));
    reg_wr(dma, DMA_S2MM_LENGTH, bytes);

    for (int i = 0; i < 100000; i++) {
        uint32_t sr = reg_rd(dma, DMA_S2MM_SR);
        if (sr & DMA_SR_ERR_IRQ) {
            fprintf(stderr, "DMA S2MM error SR=0x%08x\n", sr);
            return -1;
        }
        if ((sr & DMA_SR_IDLE) || (sr & DMA_SR_IOC_IRQ)) {
            uint32_t got = reg_rd(dma, DMA_S2MM_LENGTH);
            printf("DMA S2MM complete: %u bytes (SR=0x%08x)\n", got, sr);
            uint32_t nwords = got >> 3;
            for (uint32_t w = 0; w < (nwords < 8 ? nwords : 8); w++)
                printf("  rx[%2u] = 0x%016llx\n", w, (unsigned long long)virt_buf[w]);
            return 0;
        }
        usleep(10);
    }
    fprintf(stderr, "DMA S2MM timeout (SR=0x%08x)\n", reg_rd(dma, DMA_S2MM_SR));
    return -1;
}

static int send_mm2s_reg_rd(volatile uint32_t *csr, volatile uint32_t *dma,
                            uint64_t phys_buf, volatile uint64_t *virt_buf,
                            uint16_t artix_addr)
{
    /* Stream 0x10 command word: {opcode=0x02(RD), rsv=0x00, addr[15:0], data=32'h0} */
    reg_wr(csr, REG_TX_AXIS_SID, 0x10);
    virt_buf[0] = ((uint64_t)0x02 << 56) | ((uint64_t)artix_addr << 32);
    __sync_synchronize();

    reg_wr(dma, DMA_MM2S_CR, DMA_CR_RS);
    reg_wr(dma, DMA_MM2S_SA, (uint32_t)(phys_buf & 0xFFFFFFFFULL));
    reg_wr(dma, DMA_MM2S_SA_MSB, (uint32_t)(phys_buf >> 32));
    reg_wr(dma, DMA_MM2S_LENGTH, 8);

    for (int i = 0; i < 10000; i++) {
        uint32_t sr = reg_rd(dma, DMA_MM2S_SR);
        if (sr & (DMA_SR_IDLE | DMA_SR_IOC_IRQ)) {
            printf("DMA MM2S read-req(0x%04x) sent (SR=0x%08x)\n", artix_addr, sr);
            return 0;
        }
        usleep(10);
    }
    fprintf(stderr, "DMA MM2S timeout (SR=0x%08x)\n", reg_rd(dma, DMA_MM2S_SR));
    return -1;
}

int main(int argc, char **argv)
{
    int mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) {
        perror("open /dev/mem (run as root)");
        return 1;
    }

    volatile uint32_t *csr = (volatile uint32_t *)map_phys(mem_fd, LINK_CSR_BASE, LINK_CSR_SPAN);
    volatile uint32_t *dma = (volatile uint32_t *)map_phys(mem_fd, AXI_DMA_BASE, AXI_DMA_SPAN);
    if (!csr || !dma)
        return 1;

    dump_csrs(csr);

    if (argc > 1 && strcmp(argv[1], "--retrain") == 0) {
        reg_wr(csr, REG_LINK_CTRL, 0x4);
        usleep(50000);
        dump_csrs(csr);
    }

    uint64_t phys_addr = 0, buf_size = 0;
    if (read_sysfs_u64("/sys/class/u-dma-buf/udmabuf0/phys_addr", &phys_addr) == 0 &&
        read_sysfs_u64("/sys/class/u-dma-buf/udmabuf0/size", &buf_size) == 0 &&
        buf_size >= 8192) {
        int ufd = open("/dev/udmabuf0", O_RDWR | O_SYNC);
        if (ufd >= 0) {
            volatile uint64_t *ubuf = (volatile uint64_t *)mmap(NULL, 8192,
                                                                PROT_READ | PROT_WRITE,
                                                                MAP_SHARED, ufd, 0);
            if (ubuf != MAP_FAILED) {
                if (argc > 1 && strcmp(argv[1], "--rd-adcs") == 0)
                    send_mm2s_reg_rd(csr, dma, phys_addr, ubuf + 512, 0x0038);
                run_s2mm_capture(dma, phys_addr, ubuf, 4096);
                munmap((void *)ubuf, 8192);
            }
            close(ufd);
        }
    } else {
        printf("udmabuf0 not loaded; CSR dump complete (load u-dma-buf for DMA transfer test).\n");
    }

    munmap((void *)csr, LINK_CSR_SPAN);
    munmap((void *)dma, AXI_DMA_SPAN);
    close(mem_fd);
    return 0;
}
