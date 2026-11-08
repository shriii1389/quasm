.globl handle_qubitop2_stmt
.data
    CNgate_str: .string "CN"
    SWgate_str: .string "SW"
    CYgate_str: .string "CY"
    CZgate_str: .string "CZ"
    CP1gate_str: .string "CP1"
    CP2gate_str: .string "CP2"
    CP3gate_str: .string "CP3"
    CP4gate_str: .string "CP4"
    CP5gate_str: .string "CP5"
    CP6gate_str: .string "CP6"

.text
# qubitop2 <v>[<c>],<v>[<t>] = <gate>
# The two indices must be distinct qubits of the same register.
# a0 = 0 on success, else an error code.
handle_qubitop2_stmt:
    addi sp, sp, -48
    sw ra, 44(sp)
    sw s0, 40(sp)
    sw s1, 36(sp)
    sw s2, 32(sp)
    sw s3, 28(sp)
    sw s4, 24(sp)
    sw s5, 20(sp)

    la a0, buffer
    addi a0, a0, 8          # Skip "qubitop2"
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, op2_syntax
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    beqz t0, op2_syntax
    jal ra, find_var
    beqz a0, op2_undeclared
    mv s1, a1               # Amplitudes
    mv s2, a2               # Qubit count

    addi a0, s0, 1          # Names are a single character
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '['
    bne t0, t1, op2_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, op2_syntax
    bnez a3, op2_range
    mv s3, a0               # Control qubit
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ']'
    bne t0, t1, op2_syntax

    addi a0, a0, 1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ','
    bne t0, t1, op2_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    beqz t0, op2_syntax
    jal ra, find_var
    beqz a0, op2_undeclared
    bne a1, s1, op2_samereg # Both qubits must live in one register

    addi a0, s0, 1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '['
    bne t0, t1, op2_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, op2_syntax
    bnez a3, op2_range
    mv s4, a0               # Target qubit
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ']'
    bne t0, t1, op2_syntax

    addi a0, a0, 1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '='
    bne t0, t1, op2_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    mv s0, a0               # Gate name token

    mv t2, s0               # Nothing may follow the gate name
op2_token_end:
    lb t0, 0(t2)
    beqz t0, op2_token_done
    li t1, ' '
    beq t0, t1, op2_token_done
    li t1, 10
    beq t0, t1, op2_token_done
    li t1, 13
    beq t0, t1, op2_token_done
    addi t2, t2, 1
    j op2_token_end
op2_token_done:
    mv a0, t2
    jal ra, at_eol
    bnez a0, op2_syntax

    bgeu s3, s2, op2_index
    bgeu s4, s2, op2_index
    beq s3, s4, op2_samebit

    mv t0, s0
    la t1, CNgate_str
    jal ra, token_eq
    beqz a0, op2_cn

    mv t0, s0
    la t1, SWgate_str
    jal ra, token_eq
    beqz a0, op2_sw

    mv t0, s0
    la t1, CYgate_str
    jal ra, token_eq
    beqz a0, op2_cy

    mv t0, s0
    la t1, CZgate_str
    jal ra, token_eq
    beqz a0, op2_cz

    mv t0, s0
    la t1, CP1gate_str
    jal ra, token_eq
    beqz a0, op2_cp1

    mv t0, s0
    la t1, CP2gate_str
    jal ra, token_eq
    beqz a0, op2_cp2

    mv t0, s0
    la t1, CP3gate_str
    jal ra, token_eq
    beqz a0, op2_cp3

    mv t0, s0
    la t1, CP4gate_str
    jal ra, token_eq
    beqz a0, op2_cp4

    mv t0, s0
    la t1, CP5gate_str
    jal ra, token_eq
    beqz a0, op2_cp5

    mv t0, s0
    la t1, CP6gate_str
    jal ra, token_eq
    beqz a0, op2_cp6

    j op2_syntax

op2_cn: la s5, CNgate
        j op2_apply
op2_sw: la s5, SWgate
        j op2_apply
op2_cy: la s5, CYgate
        j op2_apply
op2_cz: la s5, CZgate
        j op2_apply
op2_cp1: la s5, CP1gate
        j op2_apply
op2_cp2: la s5, CP2gate
        j op2_apply
op2_cp3: la s5, CP3gate
        j op2_apply
op2_cp4: la s5, CP4gate
        j op2_apply
op2_cp5: la s5, CP5gate
        j op2_apply
op2_cp6: la s5, CP6gate

op2_apply:
    mv a0, s1
    mv a1, s2
    mv a2, s3
    mv a3, s4
    mv a4, s5
    jal ra, apply_gate2
    mv a0, s1               # both qubits the gate touched are exposed
    mv a1, s2
    mv a2, s3
    jal ra, apply_noise
    mv a0, s1
    mv a1, s2
    mv a2, s4
    jal ra, apply_noise
    li a0, 0
    j op2_exit

op2_syntax:
    li a0, 1
    j op2_exit
op2_undeclared:
    li a0, 2
    j op2_exit
op2_index:
    li a0, 3
    j op2_exit
op2_samebit:
    li a0, 7
    j op2_exit
op2_samereg:
    li a0, 8
    j op2_exit
op2_range:
    li a0, 17

op2_exit:
    lw s5, 20(sp)
    lw s4, 24(sp)
    lw s3, 28(sp)
    lw s2, 32(sp)
    lw s1, 36(sp)
    lw s0, 40(sp)
    lw ra, 44(sp)
    addi sp, sp, 48
    ret
