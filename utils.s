.globl starts_with
.globl token_eq
.globl prefix_match
.globl prefix_diff
.globl skip_ws
.globl at_eol
.globl parse_uint
.globl is_name_char
.globl is_reg_char

.text
# t0 = a character; a0 = 0 if it can name a classical variable: a letter.
is_name_char:
    li t1, 'A'
    blt t0, t1, inc_no
    li t1, 'Z'
    ble t0, t1, inc_yes
    li t1, 'a'
    blt t0, t1, inc_no
    li t1, 'z'
    bgt t0, t1, inc_no
inc_yes:
    li a0, 0
    ret
inc_no:
    li a0, 1
    ret

# t0 = a character; a0 = 0 if it can name a qubit register: a letter, a digit or '_'.
is_reg_char:
    li t1, '_'
    beq t0, t1, inc_yes
    li t1, '0'
    blt t0, t1, inc_no
    li t1, '9'
    ble t0, t1, inc_yes
    j is_name_char

# t0 = input, t1 = pattern; a0 = 0 if input starts with pattern.
starts_with:
    lb t2, 0(t1)
    beqz t2, prefix_match
    lb t3, 0(t0)
    beqz t3, prefix_diff
    bne t2, t3, prefix_diff
    addi t0, t0, 1
    addi t1, t1, 1
    j starts_with

token_eq:
    lb t2, 0(t1)
    beqz t2, token_eq_end
    lb t3, 0(t0)
    beqz t3, prefix_diff
    bne t2, t3, prefix_diff
    addi t0, t0, 1
    addi t1, t1, 1
    j token_eq
token_eq_end:
    lb t3, 0(t0)
    beqz t3, prefix_match
    li t2, ' '
    beq t3, t2, prefix_match
    li t2, 10           # newline
    beq t3, t2, prefix_match
    li t2, 13           # carriage return
    beq t3, t2, prefix_match
    j prefix_diff

prefix_match:
    li a0, 0
    ret

prefix_diff:
    li a0, 1
    ret

# a0 = pointer -> a0 advanced past any run of spaces. Tabs never get this far: next_line turns them into spaces.
skip_ws:
    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, skip_ws_done
    addi a0, a0, 1
    j skip_ws
skip_ws_done:
    ret

# a0 = pointer -> a0 = 0 if only trailing spaces remain before end of line.
# Comments never get this far either: next_line cuts every line at its '#'.
at_eol:
    lb t0, 0(a0)
    li t1, ' '
    beq t0, t1, at_eol_skip
    beqz t0, at_eol_yes
    li t1, 10
    beq t0, t1, at_eol_yes
    li t1, 13
    beq t0, t1, at_eol_yes
    li a0, 1
    ret
at_eol_skip:
    addi a0, a0, 1
    j at_eol
at_eol_yes:
    li a0, 0
    ret

# a0 = pointer -> a0 = value, a1 = pointer past the digits, a2 = digit count
# (a2 = 0 means there was no number there at all), a3 = 1 if the value does
# not fit in 32 bits. An overflowing number is still read to its end, so the
# caller can report it rather than a syntax error in the digits left behind.
parse_uint:
    mv t0, a0
    li t1, 0
    li t2, 0
    li t5, 0
parse_uint_loop:
    lb t3, 0(t0)
    li t4, '0'
    blt t3, t4, parse_uint_done
    li t4, '9'
    bgt t3, t4, parse_uint_done
    addi t3, t3, -48
    li t4, 10
    mulhu t6, t1, t4        # a high word means value * 10 no longer fits
    bnez t6, parse_uint_over
    mul t1, t1, t4
    add t3, t1, t3
    bltu t3, t1, parse_uint_over    # and a wrap means adding the digit did not
    mv t1, t3
    j parse_uint_next
parse_uint_over:
    li t5, 1
parse_uint_next:
    addi t0, t0, 1
    addi t2, t2, 1
    j parse_uint_loop
parse_uint_done:
    mv a0, t1
    mv a1, t0
    mv a2, t2
    mv a3, t5
    ret
