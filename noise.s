.globl handle_noise_stmt
.globl apply_noise
.data
    .align 2
    noise_str: .string "noise"
    # Depolarising rate, per qubit, per gate. 0 disables the channel, which is
    # the default and costs one float compare per gate.
    noise_p: .float 0

.text
# a0 = amplitudes, a1 = qubit count, a2 = the qubit a gate just acted on.
# With probability noise_p applies one of X, Y, Z to it, chosen uniformly --
# the quantum-trajectory form of a depolarising channel. One run is one
# trajectory, which is also what hardware hands back; the channel itself is
# what the ensemble over runs converges to.
apply_noise:
    la t0, noise_p
    flw ft0, 0(t0)
    fmv.s.x ft1, zero
    feq.s t0, ft0, ft1
    bnez t0, an_ret         # noise off: one compare and out, no frame
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    mv s0, a0
    mv s1, a1
    mv s2, a2

    jal ra, rand_unit       # fa0 = r
    la t0, noise_p
    flw ft0, 0(t0)
    flt.s t0, fa0, ft0
    beqz t0, an_exit        # this gate came through clean

    jal ra, rand_u32
    li t1, 3
    remu t0, a0, t1         # which Pauli, uniformly
    la a3, Xgate
    beqz t0, an_apply
    li t1, 1
    la a3, Ygate
    beq t0, t1, an_apply
    la a3, Zgate
an_apply:
    mv a0, s0
    mv a1, s1
    mv a2, s2
    jal ra, apply_gate1

an_exit:
    lw s2, 16(sp)
    lw s1, 20(sp)
    lw s0, 24(sp)
    lw ra, 28(sp)
    addi sp, sp, 32
an_ret:
    ret

# noise <p>  -- sets the depolarising rate applied to each qubit after each
# gate. `noise 0` turns the channel off again.
# a0 = 0 on success, else an error code.
handle_noise_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)

    la a0, buffer
    addi a0, a0, 5          # Skip "noise"
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, noise_syntax
    jal ra, skip_ws
    jal ra, parse_float
    beqz a2, noise_syntax
    bnez a3, noise_numrange
    fmv.s ft1, f0           # at_eol is a leaf, so this survives the call
    mv a0, a1
    jal ra, at_eol
    bnez a0, noise_syntax

    fmv.s.x ft2, zero       # a rate outside [0,1] is not a probability
    flt.s t0, ft1, ft2
    bnez t0, noise_range
    li t1, 1
    fcvt.s.w ft3, t1
    flt.s t0, ft3, ft1
    bnez t0, noise_range

    la t0, noise_p
    fsw ft1, 0(t0)
    li a0, 0
    j noise_exit

noise_syntax:
    li a0, 1
    j noise_exit
noise_range:
    li a0, 16
    j noise_exit
noise_numrange:
    li a0, 17

noise_exit:
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
