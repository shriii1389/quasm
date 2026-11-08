.globl handle_set_stmt
.globl handle_if_stmt
.globl handle_else_stmt
.globl handle_endif_stmt
.globl else_tail
.globl blk_else_seen
.globl eval_cond
.globl set_cvar
.globl find_cvar
.data
    .align 2
    set_str: .string "set "         # binds a classical variable.
    if_str: .string "if"            # opens a conditional.
    else_str: .string "else"        # `else`, or `else if <cond>`.
    endif_str: .string "endif"      # closes a conditional.

    # Classical variables: 8-byte entries of (name char, value), terminated
    # by a zero name, so 256 bytes holds 31 of them. Measurement outcomes
    # land here and `if` reads them; qubit registers are a separate namespace.
    .align 2                        # .space does not pad, and these are words
    cvar_table: .space 256
    # One word per open `if`, set to 1 once a branch of it has run so a later
    # `else` knows to skip instead of taking a second branch.
    .align 2
    if_stack: .space 32
    if_depth: .word 0

.text
# a0 = name pointer (only its first character is significant). a0 = 1 and
# a1 = the value on success, a3 = the entry; a0 = 0 if the name is unbound.
find_cvar:
    la t0, cvar_table
    lb t1, 0(a0)
fcv_loop:
    lw t2, 0(t0)
    beqz t2, fcv_none
    beq t1, t2, fcv_hit
    addi t0, t0, 8
    j fcv_loop
fcv_hit:
    lw a1, 4(t0)
    mv a3, t0
    li a0, 1
    ret
fcv_none:
    li a0, 0
    ret

# a0 = name pointer, a1 = value. Binds the name, rebinding in place if it is
# already bound. a0 = 0, or 15 if the table is full.
set_cvar:
    la t0, cvar_table
    addi t3, t0, 248      # last entry that still leaves a zero terminator
    lb t1, 0(a0)
scv_loop:
    lw t2, 0(t0)
    beqz t2, scv_new
    beq t1, t2, scv_bind
    addi t0, t0, 8
    blt t0, t3, scv_loop
    li a0, 15
    ret
scv_new:
    sw t1, 0(t0)
scv_bind:
    sw a1, 4(t0)
    li a0, 0
    ret

# a0 = pointer to an operand: a decimal literal, or the name of a classical
# variable. a0 = 0, a1 = its value and a2 = the pointer past it on success,
# else an error code.
parse_operand:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    jal ra, skip_ws
    mv s0, a0
    lb t0, 0(s0)
    li t1, '0'
    blt t0, t1, po_name
    li t1, '9'
    bgt t0, t1, po_name
    jal ra, parse_uint      # a literal; the first digit is already in hand
    bnez a3, po_range
    mv a2, a1
    mv a1, a0
    li a0, 0
    j po_exit

po_name:
    jal ra, is_name_char    # a name, so it has to look like one
    bnez a0, po_syntax
    mv a0, s0
    jal ra, find_cvar
    beqz a0, po_undeclared
    addi a2, s0, 1          # names are a single character
    li a0, 0
    j po_exit

po_syntax:
    li a0, 1
    j po_exit
po_undeclared:
    li a0, 2
    j po_exit
po_range:
    li a0, 17

po_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# a0 = pointer to `<x> <op> <y>`, op one of == != < <= > >=. a0 = 0 and
# a1 = 1 if the comparison holds, else an error code. Both sides are
# unsigned, since that is what a measurement outcome and `set` produce.
eval_cond:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)

    jal ra, parse_operand
    bnez a0, ev_exit
    mv s0, a1               # left value
    mv a0, a2
    jal ra, skip_ws
    mv s2, a0

    lb t0, 0(s2)
    li t1, '='
    beq t0, t1, ev_eq
    li t1, '!'
    beq t0, t1, ev_ne
    li t1, '<'
    beq t0, t1, ev_lt
    li t1, '>'
    beq t0, t1, ev_gt
    j ev_syntax

ev_eq:
    lb t0, 1(s2)            # a lone '=' is assignment, not a comparison
    li t1, '='
    bne t0, t1, ev_syntax
    li s1, 1
    addi s2, s2, 2
    j ev_rhs
ev_ne:
    lb t0, 1(s2)
    li t1, '='
    bne t0, t1, ev_syntax
    li s1, 2
    addi s2, s2, 2
    j ev_rhs
ev_lt:
    lb t0, 1(s2)
    li t1, '='
    beq t0, t1, ev_le
    li s1, 3
    addi s2, s2, 1
    j ev_rhs
ev_le:
    li s1, 4
    addi s2, s2, 2
    j ev_rhs
ev_gt:
    lb t0, 1(s2)
    li t1, '='
    beq t0, t1, ev_ge
    li s1, 5
    addi s2, s2, 1
    j ev_rhs
ev_ge:
    li s1, 6
    addi s2, s2, 2

ev_rhs:
    mv a0, s2
    jal ra, parse_operand
    bnez a0, ev_exit
    mv s2, a1               # right value
    mv a0, a2
    jal ra, at_eol
    bnez a0, ev_syntax

    li a1, 0
    li t0, 1
    beq s1, t0, ev_c_eq
    li t0, 2
    beq s1, t0, ev_c_ne
    li t0, 3
    beq s1, t0, ev_c_lt
    li t0, 4
    beq s1, t0, ev_c_le
    li t0, 5
    beq s1, t0, ev_c_gt

ev_c_ge:
    bltu s0, s2, ev_false
    j ev_true
ev_c_eq:
    bne s0, s2, ev_false
    j ev_true
ev_c_ne:
    beq s0, s2, ev_false
    j ev_true
ev_c_lt:
    bgeu s0, s2, ev_false
    j ev_true
ev_c_le:
    bltu s2, s0, ev_false
    j ev_true
ev_c_gt:
    bgeu s2, s0, ev_false

ev_true:
    li a1, 1
ev_false:
    li a0, 0
    j ev_exit

ev_syntax:
    li a0, 1

ev_exit:
    lw s2, 16(sp)
    lw s1, 20(sp)
    lw s0, 24(sp)
    lw ra, 28(sp)
    addi sp, sp, 32
    ret


# a0 = the text just past `else`. a0 = 0 on success, with a1 = 1 for a plain
# `else` or 0 for `else if`, and a2 = the condition of an `else if`; a0 = 1
# if the tail is neither. The condition is only located here, not checked:
# it is checked when, and if, it is evaluated.
else_tail:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    jal ra, skip_ws
    mv s0, a0
    jal ra, at_eol
    beqz a0, elt_plain
    mv t0, s0
    la t1, if_str
    jal ra, token_eq
    bnez a0, elt_syntax
    addi a0, s0, 2          # Skip "if"
    jal ra, skip_ws
    mv s0, a0
    jal ra, at_eol
    beqz a0, elt_syntax     # `else if` needs a condition
    mv a2, s0
    li a1, 0
    li a0, 0
    j elt_exit

elt_plain:
    li a1, 1
    li a0, 0
    j elt_exit
elt_syntax:
    li a0, 1

elt_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# a1 = 1 for a plain `else`. Records the else against the innermost `if`,
# which the caller has already checked is an `if`. a0 = 0, or 19 if that `if`
# has had its plain else already: nothing may follow one but endif.
# Leaves a1 alone.
blk_else_seen:
    la t0, blk_depth
    lw t1, 0(t0)
    addi t1, t1, -1
    li t2, 1
    sll t2, t2, t1
    la t0, blk_else
    lw t3, 0(t0)
    and t4, t3, t2
    bnez t4, bes_twice
    beqz a1, bes_ok
    or t3, t3, t2
    sw t3, 0(t0)
bes_ok:
    li a0, 0
    ret
bes_twice:
    li a0, 19
    ret

# set <v> = <n>  -- binds a classical variable to an integer. The right hand
# side may also name another classical variable.
# a0 = 0 on success, else an error code.
handle_set_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)

    la a0, buffer
    addi a0, a0, 3          # Skip "set"
    jal ra, skip_ws
    mv s0, a0               # Variable name
    lb t0, 0(s0)
    jal ra, is_name_char
    bnez a0, set_syntax
    addi a0, s0, 1          # Names are a single character
    jal ra, skip_ws
    lb t0, 0(a0)
    li t1, '='
    bne t0, t1, set_syntax
    addi a0, a0, 1
    jal ra, parse_operand
    bnez a0, set_exit
    mv s1, a1
    mv a0, a2
    jal ra, at_eol
    bnez a0, set_syntax
    mv a0, s0
    mv a1, s1
    jal ra, set_cvar
    j set_exit

set_syntax:
    li a0, 1

set_exit:
    lw s1, 4(sp)
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# if <x> <op> <y>  -- runs the lines up to the matching else/endif when the
# comparison holds, and hands the rest to skip_line when it does not. A
# condition that cannot be evaluated is reported and the whole `if` skipped.
# a0 = 0 on success, else an error code.
handle_if_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)

    la a0, buffer
    addi a0, a0, 2          # Skip "if"
    jal ra, eval_cond
    mv s0, a0               # 0, or what was wrong with the condition
    mv s1, a1               # whether it holds
    li a0, 1
    jal ra, blk_push
    bnez a0, if_exit        # 9 deep: reported, and nothing is opened

    la t0, if_depth         # blk_push has already kept this within 8
    lw t1, 0(t0)
    la t2, if_stack
    slli t3, t1, 2
    add t2, t2, t3
    addi t1, t1, 1
    sw t1, 0(t0)
    bnez s0, if_bad
    sw s1, 0(t2)            # 1 once some branch of this `if` has run
    bnez s1, if_done
    j if_skip
if_bad:
    li t3, 1                # no branch of a malformed `if` runs
    sw t3, 0(t2)
if_skip:
    la t0, skip_kind        # skip to the next else/endif of this `if`
    li t1, 2
    sw t1, 0(t0)
    la t0, blk_depth
    lw t1, 0(t0)
    la t0, skip_base
    sw t1, 0(t0)
if_done:
    mv a0, s0

if_exit:
    lw s1, 4(sp)
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# else / else if <cond>  -- only ever reached while running, which means the
# branch above it ran to completion, so the rest of the `if` is skipped and
# this branch's own condition is never evaluated. The other way in is
# skip_line, where a branch has yet to be taken and this one is a candidate.
# a0 = 0 on success, else an error code.
handle_else_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)

    jal ra, blk_top
    li t0, 1
    bne a0, t0, else_unmatched  # the innermost open construct has to be an `if`
    la a0, buffer
    addi a0, a0, 4          # Skip "else"
    jal ra, else_tail
    bnez a0, else_exit
    jal ra, blk_else_seen
    bnez a0, else_exit

    la t0, skip_kind
    li t1, 2
    sw t1, 0(t0)
    la t0, blk_depth
    lw t1, 0(t0)
    la t0, skip_base
    sw t1, 0(t0)
    li a0, 0
    j else_exit

else_unmatched:
    li a0, 14

else_exit:
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# endif  -- closes the innermost `if`.
# a0 = 0 on success, else an error code.
handle_endif_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)

    la a0, buffer
    addi a0, a0, 5          # Skip "endif"
    jal ra, at_eol
    bnez a0, endif_syntax
    jal ra, blk_top
    li t0, 1
    bne a0, t0, endif_unmatched
    jal ra, blk_pop
    la t0, if_depth
    lw t1, 0(t0)
    addi t1, t1, -1
    sw t1, 0(t0)
    li a0, 0
    j endif_exit

endif_syntax:
    li a0, 1
    j endif_exit
endif_unmatched:
    li a0, 14

endif_exit:
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
