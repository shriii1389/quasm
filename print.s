.globl check_print_cmd
.globl check_print_paren
.globl handle_print_stmt

.text
check_print_cmd:
    lb t2, 0(t1)           # Load char from print_str
    beqz t2, check_print_paren  # End of "print", check '('
    lb t3, 0(t0)           # Load char from input
    beqz t3, prefix_diff   # End of input = no match
    bne t2, t3, prefix_diff # Mismatch
    addi t0, t0, 1         # Advance input pointer
    addi t1, t1, 1         # Advance print_str pointer
    j check_print_cmd      # Continue comparison

check_print_paren:
    lb t3, 0(t0)           # Load next input char
    li t2, '('             # Check for '('
    bne t3, t2, prefix_diff # If not '(', no match
    addi t0, t0, 1         # Skip '('
    li a0, 0               # Match found
    ret

# print(<var>): prints every amplitude of the register, in basis-state order, as [(re,im),(re,im),...]. a0 = 0 on success, else an error code.
handle_print_stmt:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)

    la a0, buffer
    addi a0, a0, 6         # Skip "print("
    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    beqz t0, print_syntax
    jal ra, find_var
    beqz a0, print_undeclared
    mv s1, a1              # amplitudes
    li t0, 1
    sll s2, t0, a2         # 2^n of them

    addi a0, s0, 1         # names are a single character
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, ')'
    bne t0, t1, print_syntax
    addi a0, a0, 1
    jal ra, at_eol         # nothing may follow the closing paren
    bnez a0, print_syntax

    li a0, '['
    li a7, 11              # Syscall for character output
    ecall
print_loop:
    li a0, '('
    li a7, 11
    ecall
    flw fa0, 0(s1)         # Real part
    li a7, 2               # Syscall for float output
    ecall
    li a0, ','
    li a7, 11
    ecall
    flw fa0, 4(s1)         # Imaginary part
    li a7, 2
    ecall
    li a0, ')'
    li a7, 11
    ecall
    addi s1, s1, 8
    addi s2, s2, -1
    beqz s2, print_done
    li a0, ','
    li a7, 11
    ecall
    j print_loop

print_done:
    li a0, ']'
    li a7, 11
    ecall
    la a0, newline
    li a7, 4               # Syscall for string output
    ecall
    li a0, 0
    j print_exit

print_syntax:
    li a0, 1
    j print_exit
print_undeclared:
    li a0, 2

print_exit:
    lw s2, 16(sp)
    lw s1, 20(sp)
    lw s0, 24(sp)
    lw ra, 28(sp)
    addi sp, sp, 32
    ret
