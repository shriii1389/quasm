.globl handle_measure_stmt
.globl handle_seed_stmt
.globl rand_u32
.globl rand_unit
.data
    .align 2
    # xorshift32. Seeded to a fixed nonzero constant so a session is
    # reproducible by default; `seed <n>` picks a different stream.
    rng_state: .word 0x92D68CA2
    # Below this fraction of the register's total weight, a branch is float32
    # noise rather than a real outcome, and 1/sqrt(p) would blow the register
    # up. Relative, so an unnormalised register is judged against its own
    # weight rather than against 1. See meas_sel1.
    meas_eps: .float 0.000000001

.text
# a0 = the next xorshift32 value. Clobbers t0-t2 only.
rand_u32:
    la t0, rng_state
    lw t1, 0(t0)
    slli t2, t1, 13
    xor t1, t1, t2
    srli t2, t1, 17
    xor t1, t1, t2
    slli t2, t1, 5
    xor t1, t1, t2
    sw t1, 0(t0)
    mv a0, t1
    ret

# fa0 = a uniform sample in [0,1). Takes the top 24 bits, which is exactly
# float32's mantissa width, so every value is represented without rounding.
rand_unit:
    addi sp, sp, -16
    sw ra, 12(sp)
    jal ra, rand_u32
    srli t0, a0, 8          # 24 bits, so always non-negative
    fcvt.s.w fa0, t0
    li t0, 1
    slli t0, t0, 24
    fcvt.s.w ft0, t0
    fdiv.s fa0, fa0, ft0
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# The optional `-> <v>` tail. a0 = the text after the qubit being measured;
# a0 = 0 and a1 = the classical variable to keep the outcome in, or 0 for a
# measurement that only prints it.
meas_target:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    li t1, '-'
    beq t0, t1, mt_arrow
    jal ra, at_eol
    bnez a0, mt_syntax
    li a1, 0
    li a0, 0
    j mt_exit

mt_arrow:
    lb t0, 1(s0)
    li t1, '>'
    bne t0, t1, mt_syntax
    addi a0, s0, 2
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    jal ra, is_name_char    # a classical variable name, not a qubit register
    bnez a0, mt_syntax
    addi a0, s0, 1          # Names are a single character
    jal ra, at_eol
    bnez a0, mt_syntax
    mv a1, s0
    li a0, 0
    j mt_exit

mt_syntax:
    li a0, 1

mt_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# Keeps outcome a1 in the target the statement named, if it named one.
# s8 = the name pointer, or 0. a0 = 0, else an error code.
meas_save:
    beqz s8, ms_none
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s8
    jal ra, set_cvar
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
ms_none:
    li a0, 0
    ret

# measure <v>[<k>]  -- measures one qubit, prints |0> or |1>
# measure <v>       -- measures the whole register, prints |q0q1...qn-1>
# Either may end in `-> <c>`, which also keeps the outcome as an integer in
# the classical variable c, where `if` can read it.
# Both collapse the register in place and renormalise it.
# a0 = 0 on success, else an error code.
handle_measure_stmt:
    addi sp, sp, -48
    sw ra, 44(sp)
    sw s0, 40(sp)
    sw s1, 36(sp)
    sw s2, 32(sp)
    sw s3, 28(sp)
    sw s4, 24(sp)
    sw s5, 20(sp)
    sw s6, 16(sp)
    sw s7, 12(sp)
    sw s8, 8(sp)

    la a0, buffer
    addi a0, a0, 7          # Skip "measure"
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, meas_syntax
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    beqz t0, meas_syntax
    jal ra, find_var
    beqz a0, meas_undeclared
    mv s1, a1               # Amplitudes
    mv s2, a2               # Qubit count

    addi a0, s0, 1          # Names are a single character
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '['
    beq t0, t1, meas_one
    jal ra, meas_target
    bnez a0, meas_exit
    mv s8, a1
    j meas_all

meas_one:
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, meas_syntax
    bnez a3, meas_range
    mv s3, a0               # Target qubit
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ']'
    bne t0, t1, meas_syntax
    addi a0, a0, 1
    jal ra, meas_target
    bnez a0, meas_exit
    mv s8, a1
    bgeu s3, s2, meas_index

    li t0, 1
    sll s4, t0, s2          # 2^n amplitudes
    sub t1, s2, s3
    addi t1, t1, -1
    sll s5, t0, t1          # bit mask selecting the target qubit

    fmv.s.x fa1, zero       # weight of the branch that reads 1
    fmv.s.x fa3, zero       # weight of the branch that reads 0
    mv t2, zero
meas_p_loop:
    slli t4, t2, 3
    add t4, s1, t4
    flw ft0, 0(t4)
    flw ft1, 4(t4)
    fmul.s ft0, ft0, ft0
    fmul.s ft1, ft1, ft1
    fadd.s ft0, ft0, ft1    # |amp|^2
    and t3, t2, s5
    beqz t3, meas_p_zero
    fadd.s fa1, fa1, ft0
    j meas_p_next
meas_p_zero:
    fadd.s fa3, fa3, ft0
meas_p_next:
    addi t2, t2, 1
    blt t2, s4, meas_p_loop

    # Both branch weights are summed rather than one taken as 1 - the other,
    # so a register whose amplitudes do not sum to 1 still splits in
    # proportion to them. Scaling r by the total avoids a divide.
    fadd.s ft3, fa1, fa3    # total weight; 1.0 for a normalised register
    fmv.s.x ft4, zero
    feq.s t0, ft3, ft4
    bnez t0, meas_zeronorm  # every amplitude is zero: there is no outcome
    jal ra, rand_unit       # fa0 = r; touches only fa0 and ft0, so the
                            # weights survive it
    li t1, 1
    fcvt.s.w ft2, t1        # 1.0
    fmul.s ft7, fa0, ft3
    la t1, meas_eps
    flw ft4, 0(t1)
    fmul.s ft4, ft4, ft3    # the guard, scaled to this register's weight
    flt.s t0, ft7, fa1      # r * total < P(1) selects outcome 1
    beqz t0, meas_sel0

meas_sel1:
    li s6, 1
    fmv.s fa2, fa1
    flt.s t0, fa2, ft4      # a degenerate branch is rounding, not an outcome
    beqz t0, meas_collapse
    li s6, 0
    fmv.s fa2, fa3
    j meas_collapse
meas_sel0:
    li s6, 0
    fmv.s fa2, fa3
    flt.s t0, fa2, ft4
    beqz t0, meas_collapse
    li s6, 1
    fmv.s fa2, fa1

meas_collapse:
    fsqrt.s ft5, fa2
    fdiv.s ft5, ft2, ft5    # 1/sqrt(p), the renormalisation factor
    fmv.s.x ft6, zero
    mv t2, zero
meas_col_loop:
    and t3, t2, s5
    slli t4, t2, 3
    add t4, s1, t4
    beqz s6, meas_col_want0
    beqz t3, meas_col_zero  # outcome 1 kills every index with the bit clear
    j meas_col_keep
meas_col_want0:
    bnez t3, meas_col_zero
meas_col_keep:
    flw ft0, 0(t4)
    flw ft1, 4(t4)
    fmul.s ft0, ft0, ft5
    fmul.s ft1, ft1, ft5
    fsw ft0, 0(t4)
    fsw ft1, 4(t4)
    j meas_col_next
meas_col_zero:
    fsw ft6, 0(t4)
    fsw ft6, 4(t4)
meas_col_next:
    addi t2, t2, 1
    blt t2, s4, meas_col_loop

    mv a1, s6
    jal ra, meas_save
    bnez a0, meas_exit

    li a0, '|'
    li a7, 11               # Syscall for character output
    ecall
    addi a0, s6, 48
    li a7, 11
    ecall
    j meas_ket_close

meas_all:
    li t0, 1
    sll s4, t0, s2          # 2^n amplitudes
    fmv.s.x ft3, zero
    mv t2, zero
meas_all_total:             # total weight first, for the same reason as above
    slli t4, t2, 3
    add t4, s1, t4
    flw ft0, 0(t4)
    flw ft1, 4(t4)
    fmul.s ft0, ft0, ft0
    fmul.s ft1, ft1, ft1
    fadd.s ft0, ft0, ft1
    fadd.s ft3, ft3, ft0
    addi t2, t2, 1
    blt t2, s4, meas_all_total
    fmv.s.x fa2, zero       # constant zero, for the skip test below
    feq.s t0, ft3, fa2
    bnez t0, meas_zeronorm
    jal ra, rand_unit       # fa0 = r; touches only fa0 and ft0
    fmul.s fa0, fa0, ft3    # r scaled by the total, so an unnormalised
                            # register still samples in proportion to it
    fmv.s.x fa1, zero       # running cumulative weight
    mv t2, zero
    mv s3, zero             # chosen basis index
    li s6, 0                # set once the cumulative sum passes r
meas_all_loop:
    slli t4, t2, 3
    add t4, s1, t4
    flw ft0, 0(t4)
    flw ft1, 4(t4)
    fmul.s ft0, ft0, ft0
    fmul.s ft1, ft1, ft1
    fadd.s ft0, ft0, ft1    # |amp|^2
    fadd.s fa1, fa1, ft0
    bnez s6, meas_all_next
    feq.s t0, ft0, fa2
    bnez t0, meas_all_next  # a zero-probability index is never the outcome
    mv s3, t2               # last viable index, in case rounding starves the sum
    flt.s t0, fa0, fa1
    beqz t0, meas_all_next
    li s6, 1
meas_all_next:
    addi t2, t2, 1
    blt t2, s4, meas_all_loop

    fmv.s.x ft0, zero       # collapse onto the single chosen basis state
    mv t2, zero
    mv t4, s1
meas_all_zero:
    fsw ft0, 0(t4)
    fsw ft0, 4(t4)
    addi t4, t4, 8
    addi t2, t2, 1
    blt t2, s4, meas_all_zero
    li t0, 1
    fcvt.s.w ft0, t0
    slli t4, s3, 3
    add t4, s1, t4
    fsw ft0, 0(t4)

    mv a1, s3
    jal ra, meas_save
    bnez a0, meas_exit

    li a0, '|'
    li a7, 11
    ecall
    mv s7, s2               # bits left; qubit 0 is the most significant
meas_all_bits:
    addi s7, s7, -1
    srl t0, s3, s7
    andi t0, t0, 1
    addi a0, t0, 48
    li a7, 11
    ecall
    bnez s7, meas_all_bits

meas_ket_close:
    li a0, '>'
    li a7, 11
    ecall
    la a0, newline
    li a7, 4                # Syscall for string output
    ecall
    li a0, 0
    j meas_exit

meas_syntax:
    li a0, 1
    j meas_exit
meas_undeclared:
    li a0, 2
    j meas_exit
meas_index:
    li a0, 3
    j meas_exit
meas_range:
    li a0, 17
    j meas_exit
meas_zeronorm:
    li a0, 18

meas_exit:
    lw s8, 8(sp)
    lw s7, 12(sp)
    lw s6, 16(sp)
    lw s5, 20(sp)
    lw s4, 24(sp)
    lw s3, 28(sp)
    lw s2, 32(sp)
    lw s1, 36(sp)
    lw s0, 40(sp)
    lw ra, 44(sp)
    addi sp, sp, 48
    ret

# seed <n>  -- reseeds the measurement PRNG. n must be nonzero: xorshift32
# maps 0 to itself, so a zero seed would make every measurement return the
# same outcome forever.
# a0 = 0 on success, else an error code.
handle_seed_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    la a0, buffer
    addi a0, a0, 4          # Skip "seed"
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, seed_syntax
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, seed_syntax
    bnez a3, seed_range
    mv s0, a0
    mv a0, a1
    jal ra, at_eol
    bnez a0, seed_syntax
    beqz s0, seed_zero
    la t0, rng_state
    sw s0, 0(t0)
    li a0, 0
    j seed_exit

seed_syntax:
    li a0, 1
    j seed_exit
seed_zero:
    li a0, 9
    j seed_exit
seed_range:
    li a0, 17

seed_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
