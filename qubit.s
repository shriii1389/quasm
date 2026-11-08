.globl handle_qubit_decl
.globl parse_float
.data
    .align 2                     # accessed with lw/sw; .space does not pad
    # decl_explicit parses the whole amplitude list here before alloc_var
    # ever runs, so a malformed list (trailing garbage, a bad pair) never
    # leaves a partially- or fully-written register bound under the name.
    # Sized for the largest legal register: 64 amplitudes * 8 bytes.
    decl_amp_scratch: .space 512

.text
# qubit <v>[<n>]                    -- n-qubit register initialised to |0..0>
# qubit <v> = [(re,im),(re,im),...] -- explicit amplitudes, count a power of 2
# a0 = 0 on success, else an error code.
handle_qubit_decl:
    addi sp, sp, -48
    sw ra, 44(sp)
    sw s0, 40(sp)
    sw s1, 36(sp)
    sw s2, 32(sp)
    sw s3, 28(sp)
    sw s4, 24(sp)
    sw s5, 20(sp)
    sw s6, 16(sp)

    la a0, buffer
    addi a0, a0, 5          # Skip "qubit"
    jal ra, skip_ws
    mv s0, a0               # Variable name
    lb t0, 0(s0)
    jal ra, is_reg_char
    bnez a0, decl_syntax
    addi a0, s0, 1          # Names are a single character
    jal ra, skip_ws
    mv s1, a0
    lb t0, 0(s1)
    li t1, '['
    beq t0, t1, decl_sized
    li t1, '='
    beq t0, t1, decl_explicit
    j decl_syntax

decl_sized:
    addi a0, s1, 1
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, decl_syntax
    bnez a3, decl_range
    mv s2, a0               # Qubit count
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ']'
    bne t0, t1, decl_syntax
    addi a0, a0, 1
    jal ra, at_eol
    bnez a0, decl_syntax

    li t0, 1
    blt s2, t0, decl_size_err
    li t0, 6                # MAX_QUBITS
    bgt s2, t0, decl_size_err

    li t0, 1
    sll s3, t0, s2          # Amplitude count
    slli s4, s3, 3          # Bytes
    mv a0, s0
    mv a1, s4
    mv a2, s2
    jal ra, alloc_var
    bnez a0, decl_exit
    mv s5, a1               # Base address

    mv t0, s5               # Zero every amplitude...
    mv t1, s3
    fmv.s.x ft0, zero
decl_zero:
    fsw ft0, 0(t0)
    fsw ft0, 4(t0)
    addi t0, t0, 8
    addi t1, t1, -1
    bnez t1, decl_zero
    li t0, 1                # ...then put all the weight on |0..0>
    fcvt.s.w ft0, t0
    fsw ft0, 0(s5)
    li a0, 0
    j decl_exit

decl_explicit:
    addi a0, s1, 1          # Skip '='
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '['
    bne t0, t1, decl_syntax
    addi a0, a0, 1
    mv s1, a0               # First amplitude starts here

    mv t0, s1               # Count the (re,im) pairs before the ']'
    li s3, 0
decl_count:
    lb t1, 0(t0)
    beqz t1, decl_syntax
    li t2, ']'
    beq t1, t2, decl_counted
    li t2, '('
    bne t1, t2, decl_count_next
    addi s3, s3, 1
decl_count_next:
    addi t0, t0, 1
    j decl_count

decl_counted:
    li s2, 0                # Find n with 2^n == the amplitude count
    li t0, 1
decl_pow:
    beq t0, s3, decl_pow_done
    bgt t0, s3, decl_amp_err
    slli t0, t0, 1
    addi s2, s2, 1
    li t1, 6                # MAX_QUBITS
    bgt s2, t1, decl_amp_err
    j decl_pow
decl_pow_done:
    beqz s2, decl_amp_err   # A register needs at least one qubit

    slli s6, s3, 3          # Byte size; alloc_var waits until validated
    mv s4, s1               # Cursor into the input
    la s1, decl_amp_scratch # Write pointer: scratch, not the real register
decl_amp_loop:
    mv a0, s4
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '('
    bne t0, t1, decl_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_float
    beqz a2, decl_syntax    # an empty number is not a zero
    bnez a3, decl_range
    fsw f0, 0(s1)
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ','
    bne t0, t1, decl_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_float
    beqz a2, decl_syntax
    bnez a3, decl_range
    fsw f0, 4(s1)
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ')'
    bne t0, t1, decl_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    mv s4, a0
    addi s1, s1, 8
    addi s3, s3, -1
    beqz s3, decl_amp_done
    lb t0, 0(s4)            # another pair must follow a comma
    li t1, ','
    bne t0, t1, decl_syntax
    addi s4, s4, 1
    j decl_amp_loop

decl_amp_done:
    lb t0, 0(s4)            # and the list must close where it stops
    li t1, ']'
    bne t0, t1, decl_syntax
    addi a0, s4, 1
    jal ra, at_eol
    bnez a0, decl_syntax

    mv a0, s0                # Only now, with the whole list validated, bind
    mv a1, s6                # the name and commit storage.
    mv a2, s2
    jal ra, alloc_var
    bnez a0, decl_exit

    mv t0, a1                # Copy the validated amplitudes out of scratch
    la t1, decl_amp_scratch
    mv t2, s6
decl_amp_copy:
    lw t3, 0(t1)
    sw t3, 0(t0)
    addi t0, t0, 4
    addi t1, t1, 4
    addi t2, t2, -4
    bnez t2, decl_amp_copy
    li a0, 0
    j decl_exit

decl_syntax:
    li a0, 1
    j decl_exit
decl_size_err:
    li a0, 4
    j decl_exit
decl_amp_err:
    li a0, 6
    j decl_exit
decl_range:
    li a0, 17

decl_exit:
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

# a0 = pointer to a decimal literal: an optional '-', digits with an
# optional '.', and an optional exponent such as e-3. f0 = value, a1 = pointer
# past it, a2 = digit count (0 means there was no number there at all, which
# callers reject rather than take as a zero), a3 = 1 if it is out of range.
# Anything but zero must have a magnitude from 1e-18 up to 1e18, so that the
# squared amplitudes of a full register can neither overflow float32 nor
# underflow to zero when summed. Up to 9 significant digits are kept, more
# than float32 holds; any further digits are read and dropped, so a long
# literal loses precision rather than turning into a different number.
parse_float:
    mv t0, a0               # cursor
    li t3, 0                # the significant digits kept, as an integer
    li t4, 0                # how many of them
    li t5, 0                # decimal exponent: the value is t3 * 10^t5
    li t6, 0                # digits read in all
    li a4, 0                # negative
    li a3, 0

    lb t1, 0(t0)
    li t2, '-'
    bne t1, t2, pf_int
    li a4, 1
    addi t0, t0, 1

pf_int:
    lb t1, 0(t0)
    li t2, '0'
    blt t1, t2, pf_point
    li t2, '9'
    bgt t1, t2, pf_point
    addi t1, t1, -48
    addi t6, t6, 1
    addi t0, t0, 1
    or t2, t3, t1
    beqz t2, pf_int         # a leading zero changes nothing
    li t2, 9
    bge t4, t2, pf_int_drop
    li t2, 10
    mul t3, t3, t2
    add t3, t3, t1
    addi t4, t4, 1
    j pf_int
pf_int_drop:
    addi t5, t5, 1          # a dropped digit before the point still scales it
    j pf_int

pf_point:
    li t2, '.'
    bne t1, t2, pf_digits_done
    addi t0, t0, 1
pf_frac:
    lb t1, 0(t0)
    li t2, '0'
    blt t1, t2, pf_digits_done
    li t2, '9'
    bgt t1, t2, pf_digits_done
    addi t1, t1, -48
    addi t6, t6, 1
    addi t0, t0, 1
    or t2, t3, t1
    beqz t2, pf_frac_zero
    li t2, 9
    bge t4, t2, pf_frac     # past the ninth significant digit: dropped
    li t2, 10
    mul t3, t3, t2
    add t3, t3, t1
    addi t4, t4, 1
    addi t5, t5, -1
    j pf_frac
pf_frac_zero:
    addi t5, t5, -1         # a leading zero after the point shifts it down
    j pf_frac

pf_digits_done:
    beqz t6, pf_none
    li t2, 'e'
    beq t1, t2, pf_exp
    li t2, 'E'
    bne t1, t2, pf_range
pf_exp:
    addi a5, t0, 1          # only an exponent with digits belongs to the number
    li a6, 1
    lb t1, 0(a5)
    li t2, '+'
    beq t1, t2, pf_exp_sign
    li t2, '-'
    bne t1, t2, pf_exp_first
    li a6, -1
pf_exp_sign:
    addi a5, a5, 1
pf_exp_first:
    lb t1, 0(a5)
    li t2, '0'
    blt t1, t2, pf_range    # "1e" stops before the e, and the caller rejects it
    li t2, '9'
    bgt t1, t2, pf_range
    li a2, 0
pf_exp_loop:
    lb t1, 0(a5)
    li t2, '0'
    blt t1, t2, pf_exp_done
    li t2, '9'
    bgt t1, t2, pf_exp_done
    addi t1, t1, -48
    li t2, 1000
    bge a2, t2, pf_exp_next # far out of range already; stop growing
    li t2, 10
    mul a2, a2, t2
    add a2, a2, t1
pf_exp_next:
    addi a5, a5, 1
    j pf_exp_loop
pf_exp_done:
    mul a2, a2, a6
    add t5, t5, a2
    mv t0, a5

pf_range:
    fmv.s.x f0, zero
    beqz t3, pf_sign        # zero is always in range
    add t1, t5, t4
    addi t1, t1, -1         # the power of ten of the leading digit
    li t2, 17
    bgt t1, t2, pf_out
    li t2, -18
    blt t1, t2, pf_out
    fcvt.s.w f0, t3
    li t1, 10
    fcvt.s.w f1, t1
    li t1, 1
    fcvt.s.w f2, t1         # 10^|t5|, exact in float32 up to 10^10
    mv t1, t5
    bgez t1, pf_pow
    neg t1, t1
pf_pow:
    beqz t1, pf_scale
    fmul.s f2, f2, f1
    addi t1, t1, -1
    j pf_pow
pf_scale:
    bltz t5, pf_div
    fmul.s f0, f0, f2
    j pf_sign
pf_div:
    fdiv.s f0, f0, f2       # one rounding, so e.g. 0.70710678 lands where it always did
pf_sign:
    beqz a4, pf_done
    fneg.s f0, f0
    j pf_done
pf_out:
    li a3, 1
    j pf_done
pf_none:
    fmv.s.x f0, zero

pf_done:
    mv a1, t0
    mv a2, t6
    ret
