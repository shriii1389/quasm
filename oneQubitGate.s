.globl handle_qubitop1_stmt
.data
    Hgate_str: .string "H"
    Igate_str: .string "I"
    Xgate_str: .string "X"
    Ygate_str: .string "Y"
    Zgate_str: .string "Z"
    Sgate_str: .string "S"
    Tgate_str: .string "T"
    SNgate_str: .string "SN"
    SDGgate_str: .string "SDG"
    TDGgate_str: .string "TDG"

.text
# qubitop1 <v>[<k>] = <gate>   -- applies a single-qubit gate to qubit k.
# a0 = 0 on success, else an error code.
handle_qubitop1_stmt:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    sw s3, 12(sp)
    sw s4, 8(sp)

    la a0, buffer
    addi a0, a0, 8          # Skip "qubitop1"
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, op1_syntax
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    beqz t0, op1_syntax
    jal ra, find_var
    beqz a0, op1_undeclared
    mv s1, a1               # Amplitudes
    mv s2, a2               # Qubit count

    addi a0, s0, 1          # Names are a single character
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '['
    bne t0, t1, op1_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, op1_syntax
    bnez a3, op1_range
    mv s3, a0               # Target qubit
    mv a0, a1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ']'
    bne t0, t1, op1_syntax

    addi a0, a0, 1
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '='
    bne t0, t1, op1_syntax
    addi a0, a0, 1
    jal ra, skip_ws
    mv s0, a0               # Gate name token

    mv t2, s0               # Nothing may follow the gate name
op1_token_end:
    lb t0, 0(t2)
    beqz t0, op1_token_done
    li t1, ' '
    beq t0, t1, op1_token_done
    li t1, 10
    beq t0, t1, op1_token_done
    li t1, 13
    beq t0, t1, op1_token_done
    addi t2, t2, 1
    j op1_token_end
op1_token_done:
    mv a0, t2
    jal ra, at_eol
    bnez a0, op1_syntax

    bgeu s3, s2, op1_index

    mv t0, s0               # SN first: "S" would otherwise shadow it
    la t1, SNgate_str
    jal ra, token_eq
    beqz a0, op1_sn

    mv t0, s0
    la t1, Hgate_str
    jal ra, token_eq
    beqz a0, op1_h

    mv t0, s0
    la t1, Igate_str
    jal ra, token_eq
    beqz a0, op1_i

    mv t0, s0
    la t1, Xgate_str
    jal ra, token_eq
    beqz a0, op1_x

    mv t0, s0
    la t1, Ygate_str
    jal ra, token_eq
    beqz a0, op1_y

    mv t0, s0
    la t1, Zgate_str
    jal ra, token_eq
    beqz a0, op1_z

    mv t0, s0
    la t1, Sgate_str
    jal ra, token_eq
    beqz a0, op1_s

    mv t0, s0
    la t1, Tgate_str
    jal ra, token_eq
    beqz a0, op1_t

    mv t0, s0
    la t1, SDGgate_str
    jal ra, token_eq
    beqz a0, op1_sdg

    mv t0, s0
    la t1, TDGgate_str
    jal ra, token_eq
    beqz a0, op1_tdg

    j op1_syntax

op1_h:  la s4, Hgate
        j op1_apply
op1_i:  la s4, Igate
        j op1_apply
op1_x:  la s4, Xgate
        j op1_apply
op1_y:  la s4, Ygate
        j op1_apply
op1_z:  la s4, Zgate
        j op1_apply
op1_s:  la s4, Sgate
        j op1_apply
op1_t:  la s4, Tgate
        j op1_apply
op1_sn: la s4, SNgate
        j op1_apply
op1_sdg: la s4, SDGgate
        j op1_apply
op1_tdg: la s4, TDGgate

op1_apply:
    mv a0, s1
    mv a1, s2
    mv a2, s3
    mv a3, s4
    jal ra, apply_gate1
    mv a0, s1               # a gate is where decoherence enters
    mv a1, s2
    mv a2, s3
    jal ra, apply_noise
    li a0, 0
    j op1_exit

op1_syntax:
    li a0, 1
    j op1_exit
op1_undeclared:
    li a0, 2
    j op1_exit
op1_index:
    li a0, 3
    j op1_exit
op1_range:
    li a0, 17

op1_exit:
    lw s4, 8(sp)
    lw s3, 12(sp)
    lw s2, 16(sp)
    lw s1, 20(sp)
    lw s0, 24(sp)
    lw ra, 28(sp)
    addi sp, sp, 32
    ret
