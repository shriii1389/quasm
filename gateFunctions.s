.globl apply_gate1
.globl apply_gate2

# Bit-indexed statevector kernel. A register of n qubits is 2^n contiguous
# amplitudes, each stored as (re, im) float32 pair. Qubit 0 is the *most*
# significant bit of an amplitude index, matching the |q0 q1 ... qn-1> basis
# ordering, so qubit j occupies bit (n-1-j).

.text
# a0 = amplitudes, a1 = qubit count n, a2 = target qubit, a3 = 2x2 matrix
# (row-major, each entry an (re, im) pair). Acts in place.
apply_gate1:
    li t0, 1
    sll t1, t0, a1          # 2^n amplitudes
    sub t2, a1, a2
    addi t2, t2, -1
    sll t2, t0, t2          # bit mask selecting the target qubit

    flw ft0, 0(a3)          # u00
    flw ft1, 4(a3)
    flw ft2, 8(a3)          # u01
    flw ft3, 12(a3)
    flw ft4, 16(a3)         # u10
    flw ft5, 20(a3)
    flw ft6, 24(a3)         # u11
    flw ft7, 28(a3)

    mv t3, zero             # amplitude index
g1_loop:
    and t4, t3, t2
    bnez t4, g1_next        # visit each pair once, from its low index
    or t5, t3, t2
    slli t6, t3, 3
    add t6, a0, t6          # &state[i]
    slli a4, t5, 3
    add a4, a0, a4          # &state[i | mask]

    flw ft8, 0(t6)          # a = state[i]
    flw ft9, 4(t6)
    flw ft10, 0(a4)         # b = state[i | mask]
    flw ft11, 4(a4)

    fmul.s fa0, ft0, ft8    # (u00*a + u01*b).re
    fmul.s fa4, ft1, ft9
    fsub.s fa0, fa0, fa4
    fmul.s fa4, ft2, ft10
    fadd.s fa0, fa0, fa4
    fmul.s fa4, ft3, ft11
    fsub.s fa0, fa0, fa4

    fmul.s fa1, ft0, ft9    # (u00*a + u01*b).im
    fmul.s fa4, ft1, ft8
    fadd.s fa1, fa1, fa4
    fmul.s fa4, ft2, ft11
    fadd.s fa1, fa1, fa4
    fmul.s fa4, ft3, ft10
    fadd.s fa1, fa1, fa4

    fmul.s fa2, ft4, ft8    # (u10*a + u11*b).re
    fmul.s fa4, ft5, ft9
    fsub.s fa2, fa2, fa4
    fmul.s fa4, ft6, ft10
    fadd.s fa2, fa2, fa4
    fmul.s fa4, ft7, ft11
    fsub.s fa2, fa2, fa4

    fmul.s fa3, ft4, ft9    # (u10*a + u11*b).im
    fmul.s fa4, ft5, ft8
    fadd.s fa3, fa3, fa4
    fmul.s fa4, ft6, ft11
    fadd.s fa3, fa3, fa4
    fmul.s fa4, ft7, ft10
    fadd.s fa3, fa3, fa4

    fsw fa0, 0(t6)          # both new values are ready before either store
    fsw fa1, 4(t6)
    fsw fa2, 0(a4)
    fsw fa3, 4(a4)
g1_next:
    addi t3, t3, 1
    blt t3, t1, g1_loop
    ret

# a0 = amplitudes, a1 = qubit count n, a2 = control qubit, a3 = target qubit,
# a4 = 4x4 matrix (row-major, (re, im) entries). Acts in place. The matrix is
# indexed as 2*control_bit + target_bit, so it reads as |control target>
# regardless of which way round the two qubits sit in the register.
apply_gate2:
    addi sp, sp, -32
    sw s0, 28(sp)
    sw s1, 24(sp)
    sw s2, 20(sp)
    sw s3, 16(sp)
    sw s4, 12(sp)
    sw s5, 8(sp)
    sw s6, 4(sp)

    li t0, 1
    sll s0, t0, a1          # 2^n amplitudes
    sub t1, a1, a2
    addi t1, t1, -1
    sll s1, t0, t1          # control bit mask
    sub t1, a1, a3
    addi t1, t1, -1
    sll s2, t0, t1          # target bit mask
    or s3, s1, s2

    mv s4, zero             # amplitude index
g2_loop:
    and t0, s4, s3
    bnez t0, g2_next        # visit each group of four once, from |00>

    la t6, g2_addr          # the four amplitudes this group touches
    slli t1, s4, 3
    add t1, a0, t1
    sw t1, 0(t6)            # |00>
    or t1, s4, s2
    slli t1, t1, 3
    add t1, a0, t1
    sw t1, 4(t6)            # |01>
    or t1, s4, s1
    slli t1, t1, 3
    add t1, a0, t1
    sw t1, 8(t6)            # |10>
    or t1, s4, s3
    slli t1, t1, 3
    add t1, a0, t1
    sw t1, 12(t6)           # |11>

    la t0, g2_amp           # gather them into a contiguous vector
    li t2, 4
g2_gather:
    lw t1, 0(t6)
    lw t5, 0(t1)
    sw t5, 0(t0)
    lw t5, 4(t1)
    sw t5, 4(t0)
    addi t6, t6, 4
    addi t0, t0, 8
    addi t2, t2, -1
    bnez t2, g2_gather

    mv t3, a4               # walks the 16 matrix entries in row-major order
    la t4, g2_tmp
    li s5, 4                # rows left
g2_row:
    fmv.s.x fa0, zero
    fmv.s.x fa1, zero
    la t5, g2_amp
    li s6, 4                # columns left
g2_col:
    flw ft0, 0(t3)          # m
    flw ft1, 4(t3)
    flw ft2, 0(t5)          # v
    flw ft3, 4(t5)
    fmul.s ft4, ft0, ft2
    fmul.s ft5, ft1, ft3
    fsub.s ft4, ft4, ft5
    fadd.s fa0, fa0, ft4
    fmul.s ft4, ft0, ft3
    fmul.s ft5, ft1, ft2
    fadd.s ft4, ft4, ft5
    fadd.s fa1, fa1, ft4
    addi t3, t3, 8
    addi t5, t5, 8
    addi s6, s6, -1
    bnez s6, g2_col
    fsw fa0, 0(t4)
    fsw fa1, 4(t4)
    addi t4, t4, 8
    addi s5, s5, -1
    bnez s5, g2_row

    la t6, g2_addr          # scatter the results back
    la t0, g2_tmp
    li t2, 4
g2_scatter:
    lw t1, 0(t6)
    lw t5, 0(t0)
    sw t5, 0(t1)
    lw t5, 4(t0)
    sw t5, 4(t1)
    addi t6, t6, 4
    addi t0, t0, 8
    addi t2, t2, -1
    bnez t2, g2_scatter

g2_next:
    addi s4, s4, 1
    blt s4, s0, g2_loop

    lw s6, 4(sp)
    lw s5, 8(sp)
    lw s4, 12(sp)
    lw s3, 16(sp)
    lw s2, 20(sp)
    lw s1, 24(sp)
    lw s0, 28(sp)
    addi sp, sp, 32
    ret
