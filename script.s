.globl next_line
.globl skip_line
.globl abort_loops
.globl handle_repeat_stmt
.globl handle_endrepeat_stmt
.globl handle_end_stmt
.globl blk_push
.globl blk_top
.globl blk_pop
.data
    .align 2
    repeat_str: .string "repeat"        # loop head; the count follows.
    endrepeat_str: .string "endrepeat"  # loop tail.
    err_eof: .string "Unexpected end of input\n"

    # A loop body has to be read twice, so lines are copied here as they
    # arrive -- but only while a loop is open, and the store is dropped the
    # moment the outermost loop closes, so straight-line programs of any
    # length never touch it. Each line is kept as its two-byte line number
    # followed by its text, so an error on a replayed line names the right line.
    prog_store: .space 2048
    .align 2
    prog_end: .word 0           # bump pointer; main initialises it.
    replay_ptr: .word 0         # 0 = take the next line from stdin.
    line_count: .word 0         # lines read from stdin so far
    cur_line: .word 0           # the line the current statement came from

    # One (body address, iterations left) frame per running loop.
    loop_stack: .space 64
    loop_depth: .word 0

    # Every construct open at this point in the text, innermost last, whether
    # it is running or being skipped: bit i of blk_kind is 1 for an `if` and 0
    # for a `repeat`, and bit i of blk_else is set once that `if` has had its
    # plain `else`. Tracking skipped constructs too is what lets a skipped
    # region be checked for block structure without running any of it.
    blk_kind: .word 0
    blk_else: .word 0
    blk_depth: .word 0
    blk_loops: .word 0          # repeats open, for the 8-deep limit
    blk_ifs: .word 0            # ifs open, likewise

    # Lines are read but not run while skip_kind is set: 1 = the body of a
    # `repeat 0`, or of loops the store could not hold, ending at its
    # `endrepeat`; 2 = a branch of an `if` that was not taken, ending at the
    # next else/endif; 3 = the rest of the program after an `end` inside a
    # block, ending at the top-level `end`. skip_base is the blk_depth of the
    # construct the skip belongs to, so only the closer at that depth ends it.
    skip_kind: .word 0
    skip_base: .word 0
    blank_run: .word 0          # consecutive empty lines; see eof_guard.

.text
# Fills `buffer` with the next statement, from the loop store while a loop is
# replaying and from stdin otherwise. a0 = 0, or an error code if the line was
# too long or the store overflowed.
next_line:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    la s0, replay_ptr
    lw t1, 0(s0)
    beqz t1, nl_stdin
    la t2, prog_end
    lw t2, 0(t2)
    bltu t1, t2, nl_replay
    sw zero, 0(s0)              # replay ran out; the rest comes from stdin

nl_stdin:
    la a0, prompt
    li a7, 4                    # Syscall for printing a string.
    ecall
    la a0, buffer
    li a1, 1024                 # Maximum input length.
    li a7, 8                    # Syscall for reading a string.
    ecall
    jal ra, eof_guard
    la t0, line_count
    lw t1, 0(t0)
    addi t1, t1, 1
    sw t1, 0(t0)
    la t0, cur_line
    sw t1, 0(t0)
    jal ra, line_fits
    bnez a0, nl_exit            # never run and never recorded
    jal ra, normalise_line
    la t0, loop_depth
    lw t0, 0(t0)
    beqz t0, nl_ok              # nothing to replay it for
    jal ra, record_line
    beqz a0, nl_exit
    jal ra, discard_loops       # the store filled up; a0 survives the call
    j nl_exit

nl_replay:
    lbu t3, 0(t1)               # the line number, low byte first
    lbu t4, 1(t1)
    slli t4, t4, 8
    or t3, t3, t4
    la t2, cur_line
    sw t3, 0(t2)
    addi t1, t1, 2
    la t2, buffer
nl_copy:
    lb t3, 0(t1)
    sb t3, 0(t2)
    addi t1, t1, 1
    addi t2, t2, 1
    bnez t3, nl_copy
    sw t1, 0(s0)

nl_ok:
    li a0, 0
nl_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# The read syscall stores at most 1023 bytes and drops the rest of a longer
# line, so a buffer that filled up without reaching the newline has lost part
# of its line -- which might otherwise still parse, as something else.
# a0 = 20 if so, else 0.
line_fits:
    la t0, buffer
    li t2, 1023
    add t2, t0, t2
lf_loop:
    lb t1, 0(t0)
    beqz t1, lf_end
    li t3, 10                   # newline
    beq t1, t3, lf_ok
    addi t0, t0, 1
    j lf_loop
lf_end:
    bltu t0, t2, lf_ok          # the line ended early, so all of it is here
    li a0, 20
    ret
lf_ok:
    li a0, 0
    ret

# Makes a line read the same however it is laid out: a tab is a space, a '#'
# ends the line, and leading spaces are dropped so that a line can be indented.
normalise_line:
    la t0, buffer
nm_scan:
    lb t1, 0(t0)
    beqz t1, nm_strip
    li t2, 9                    # tab
    bne t1, t2, nm_hash
    li t1, ' '
    sb t1, 0(t0)
nm_hash:
    li t2, '#'
    bne t1, t2, nm_next
    sb zero, 0(t0)              # the comment is gone
    j nm_strip
nm_next:
    addi t0, t0, 1
    j nm_scan
nm_strip:
    la t0, buffer
    mv t1, t0
nm_lead:
    lb t2, 0(t1)
    li t3, ' '
    bne t2, t3, nm_shift
    addi t1, t1, 1
    j nm_lead
nm_shift:
    beq t1, t0, nm_ret          # nothing to strip
nm_copy:
    lb t2, 0(t1)
    sb t2, 0(t0)
    addi t0, t0, 1
    addi t1, t1, 1
    bnez t2, nm_copy
nm_ret:
    ret

# RARS hands back "\n" both for an empty line and at end of input, so a
# program that never says `end` would otherwise sit in input_loop forever.
# A run of empty lines this long is end of input, not formatting.
eof_guard:
    la t0, buffer
    lb t1, 0(t0)
    la t2, blank_run
    beqz t1, eof_count
    li t3, 10                   # newline
    beq t1, t3, eof_count
    sw zero, 0(t2)
    ret
eof_count:
    lw t1, 0(t2)
    addi t1, t1, 1
    sw t1, 0(t2)
    li t3, 32                   # MAX_BLANK_RUN
    blt t1, t3, eof_ret
    la a0, err_eof
    li a7, 4
    ecall
    li a7, 10                   # Syscall to terminate execution.
    ecall
eof_ret:
    ret

# Appends the current line number and `buffer`, terminator included, to the
# loop store. a0 = 0, or 10 if the store is full.
record_line:
    la t0, prog_end
    lw t1, 0(t0)
    la t2, prog_store
    li t3, 2048
    add t2, t2, t3              # one past the end of the store
    addi t4, t1, 2
    bltu t2, t4, rec_full
    la t3, cur_line
    lw t3, 0(t3)
    sb t3, 0(t1)
    srli t3, t3, 8
    sb t3, 1(t1)
    addi t1, t1, 2
    la t3, buffer
rec_copy:
    bgeu t1, t2, rec_full
    lb t4, 0(t3)
    sb t4, 0(t1)
    addi t1, t1, 1
    addi t3, t3, 1
    bnez t4, rec_copy
    sw t1, 0(t0)                # only committed once the whole line fits
    li a0, 0
    ret
rec_full:
    li a0, 10
    ret

# The store filled up part way through a body, so none of the open loops can
# ever replay correctly. All of them are still on their first pass -- lines
# are only ever recorded while reading stdin -- so the rest of their bodies
# is still ahead in the input, and skipping to the outermost loop's
# `endrepeat` lands exactly where they would have ended. Whatever was opened
# inside that loop becomes part of the skipped text; the `if`s around it stay
# open and running. Leaves a0 alone for the caller to report.
discard_loops:
    la t0, loop_depth
    lw t1, 0(t0)
    beqz t1, disc_ret
    sw zero, 0(t0)
    la t0, blk_kind
    lw t0, 0(t0)
    li t1, 0                    # the outermost loop is the lowest 0 bit:
disc_find:                      # everything below it is a running `if`
    srl t2, t0, t1
    andi t2, t2, 1
    beqz t2, disc_found
    addi t1, t1, 1
    j disc_find
disc_found:
    la t0, if_depth
    sw t1, 0(t0)                # the ifs inside the loop are skipped text now
    addi t1, t1, 1
    la t0, skip_base
    sw t1, 0(t0)
    la t0, skip_kind
    li t1, 1
    sw t1, 0(t0)
    la t0, replay_ptr
    sw zero, 0(t0)
    la t0, prog_end
    la t1, prog_store
    sw t1, 0(t0)
disc_ret:
    ret

# a0 = the kind of construct opening (0 = repeat, 1 = if), recorded as the
# innermost open construct. a0 = 0, or 11/13 if that kind is already open 8
# deep, in which case nothing is recorded.
blk_push:
    la t0, blk_loops
    li t2, 11
    beqz a0, bp_count
    la t0, blk_ifs
    li t2, 13
bp_count:
    lw t1, 0(t0)
    li t3, 8                    # MAX_LOOP_DEPTH, MAX_IF_DEPTH
    bge t1, t3, bp_deep
    addi t1, t1, 1
    sw t1, 0(t0)
    la t0, blk_depth
    lw t1, 0(t0)
    li t3, 1
    sll t3, t3, t1              # this construct's bit
    not t6, t3
    la t4, blk_else
    lw t5, 0(t4)
    and t5, t5, t6              # a fresh `if` has had no else yet
    sw t5, 0(t4)
    la t4, blk_kind
    lw t5, 0(t4)
    and t5, t5, t6
    beqz a0, bp_kind
    or t5, t5, t3
bp_kind:
    sw t5, 0(t4)
    addi t1, t1, 1
    sw t1, 0(t0)
    li a0, 0
    ret
bp_deep:
    mv a0, t2
    ret

# a0 = the kind of the innermost open construct (0 = repeat, 1 = if), or -1
# when nothing is open.
blk_top:
    la t0, blk_depth
    lw t1, 0(t0)
    beqz t1, bt_none
    addi t1, t1, -1
    la t0, blk_kind
    lw t0, 0(t0)
    srl t0, t0, t1
    andi a0, t0, 1
    ret
bt_none:
    li a0, -1
    ret

# Closes the innermost open construct.
blk_pop:
    la t0, blk_depth
    lw t1, 0(t0)
    addi t1, t1, -1
    sw t1, 0(t0)
    la t0, blk_kind
    lw t0, 0(t0)
    srl t0, t0, t1
    andi t0, t0, 1
    la t2, blk_loops
    beqz t0, bpop_count
    la t2, blk_ifs
bpop_count:
    lw t3, 0(t2)
    addi t3, t3, -1
    sw t3, 0(t2)
    ret

# a0 = the text after `repeat`. a0 = 0 and a1 = the count, else an error
# code. Shared with skip_line, so a skipped loop head is held to the same
# shape as one that runs.
repeat_count:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    lb t0, 0(a0)
    li t1, ' '
    bne t0, t1, rc_syntax       # the count needs a space before it
    jal ra, skip_ws
    jal ra, parse_uint
    beqz a2, rc_syntax
    bnez a3, rc_range
    mv s0, a0
    mv a0, a1
    jal ra, at_eol
    bnez a0, rc_syntax
    mv a1, s0
    li a0, 0
    j rc_exit

rc_syntax:
    li a0, 1
    j rc_exit
rc_range:
    li a0, 17

rc_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# repeat <n>  -- runs the lines up to the matching `endrepeat` n times.
# a0 = 0 on success, else an error code.
handle_repeat_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)

    la a0, buffer
    addi a0, a0, 6          # Skip "repeat"
    jal ra, repeat_count
    mv s0, a0               # 0, or what was wrong with the loop head
    mv s1, a1               # Iteration count
    li a0, 0
    jal ra, blk_push
    bnez a0, rep_exit       # 9 deep: reported, and nothing is opened
    bnez s0, rep_skip       # a malformed head runs its body no times at all
    beqz s1, rep_skip       # `repeat 0` reads the body but runs none of it

    la t0, loop_depth       # blk_push has already kept this within 8
    lw t1, 0(t0)
    la t3, loop_stack
    slli t4, t1, 3          # frames are (body address, iterations left)
    add t3, t3, t4

    la t4, replay_ptr       # the body starts at the next line, wherever that
    lw t4, 0(t4)            # line is going to come from
    bnez t4, rep_push
    la t4, prog_end
    lw t4, 0(t4)
rep_push:
    sw t4, 0(t3)
    sw s1, 4(t3)
    addi t1, t1, 1
    sw t1, 0(t0)
    li a0, 0
    j rep_exit

rep_skip:
    la t0, skip_kind        # nothing is skipped yet, or main would not have
    li t1, 1                # dispatched this statement at all
    sw t1, 0(t0)
    la t0, blk_depth
    lw t1, 0(t0)
    la t0, skip_base
    sw t1, 0(t0)
    mv a0, s0

rep_exit:
    lw s1, 4(sp)
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# endrepeat  -- another iteration if the innermost loop has any left, else
# closes it. a0 = 0 on success, else an error code.
handle_endrepeat_stmt:
    addi sp, sp, -16
    sw ra, 12(sp)

    la a0, buffer
    addi a0, a0, 9          # Skip "endrepeat"
    jal ra, at_eol
    bnez a0, endr_syntax
    jal ra, blk_top
    bnez a0, endr_unmatched # the innermost open construct has to be a loop

    la t0, loop_depth       # and, since nothing is being skipped, a running one
    lw t1, 0(t0)
    la t2, loop_stack
    addi t3, t1, -1
    slli t3, t3, 3
    add t2, t2, t3          # the innermost frame
    lw t3, 4(t2)
    addi t3, t3, -1
    beqz t3, endr_close
    sw t3, 4(t2)
    lw t3, 0(t2)
    la t4, replay_ptr
    sw t3, 0(t4)            # next line comes from the top of the body
    li a0, 0
    j endr_exit

endr_close:
    addi t1, t1, -1
    sw t1, 0(t0)
    jal ra, blk_pop
    jal ra, loops_settled
    li a0, 0
    j endr_exit

endr_syntax:
    li a0, 1
    j endr_exit
endr_unmatched:
    li a0, 12

endr_exit:
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# end  -- stops the program. Inside a block, the rest of the text is still
# read up to the top-level `end`, without running any of it, so that a block
# the program never closes is reported rather than silently ignored. Returns
# only in that case.
handle_end_stmt:
    la t0, blk_depth
    lw t1, 0(t0)
    bnez t1, end_drain
    li a7, 10               # Syscall to terminate execution.
    ecall
end_drain:
    la t0, replay_ptr
    lw t2, 0(t0)
    beqz t2, end_skip       # reading stdin: what is open is what the text has open
    sw zero, 0(t0)          # replaying: stdin is already past the outermost
    la t3, blk_kind         # loop's endrepeat, so everything from that loop
    lw t3, 0(t3)            # inwards is closed in the text
    li t4, 0
end_find:
    srl t5, t3, t4
    andi t5, t5, 1
    beqz t5, end_found
    addi t4, t4, 1
    j end_find
end_found:
    la t5, blk_depth
    sw t4, 0(t5)
    la t5, blk_ifs          # all that is left open below it is `if`s
    sw t4, 0(t5)
    la t5, blk_loops
    sw zero, 0(t5)
end_skip:
    la t0, loop_depth       # nothing runs again, so nothing needs recording
    sw zero, 0(t0)
    la t0, prog_end
    la t1, prog_store
    sw t1, 0(t0)
    la t0, skip_kind
    li t1, 3
    sw t1, 0(t0)
    la t0, skip_base
    sw zero, 0(t0)
    ret

# Called whenever a loop closes: with none left open there is nothing to
# replay, so the store goes back to empty and reading resumes from stdin.
loops_settled:
    la t0, loop_depth
    lw t0, 0(t0)
    bnez t0, ls_ret
    la t0, replay_ptr
    sw zero, 0(t0)
    la t0, prog_end
    la t1, prog_store
    sw t1, 0(t0)
ls_ret:
    ret

# An error inside a loop breaks out of it rather than repeating itself once
# per iteration: every open loop finishes the iteration it is in and stops.
# Touches nothing a caller could care about, a0 included.
abort_loops:
    la t0, loop_depth
    lw t1, 0(t0)
    beqz t1, ab_ret
    la t2, loop_stack
    li t3, 1
ab_loop:
    sw t3, 4(t2)
    addi t2, t2, 8
    addi t1, t1, -1
    bnez t1, ab_loop
ab_ret:
    ret

# A line that is being read but not run. Only the keywords that open or close
# a block matter, and those are held to the same rules as when they run, so a
# skipped region still has to be well formed. a0 = 0, or an error code.
skip_line:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)

    la t0, buffer
    la t1, repeat_str
    jal ra, token_eq
    beqz a0, sk_repeat
    la t0, buffer
    la t1, if_str
    jal ra, token_eq
    beqz a0, sk_if
    la t0, buffer
    la t1, endrepeat_str
    jal ra, token_eq
    beqz a0, sk_endrepeat
    la t0, buffer
    la t1, endif_str
    jal ra, token_eq
    beqz a0, sk_endif
    la t0, buffer
    la t1, else_str
    jal ra, token_eq
    beqz a0, sk_else

    la t0, skip_kind        # after an `end` inside a block, the program
    lw t0, 0(t0)            # stops at the top-level `end`
    li t1, 3
    bne t0, t1, sk_none
    la t0, blk_depth
    lw t0, 0(t0)
    bnez t0, sk_none
    la t0, buffer
    la t1, end_str
    jal ra, token_eq
    bnez a0, sk_none
    la a0, buffer
    addi a0, a0, 3          # Skip "end"
    jal ra, at_eol
    bnez a0, sk_none
    li a7, 10               # Syscall to terminate execution.
    ecall

sk_repeat:
    la a0, buffer
    addi a0, a0, 6          # Skip "repeat"
    jal ra, repeat_count
    mv s0, a0
    li a0, 0
    jal ra, blk_push
    bnez a0, sk_exit        # too deep: reported, and not counted
    mv a0, s0
    j sk_exit

sk_if:
    la a0, buffer
    addi a0, a0, 2          # Skip "if"
    jal ra, skip_ws
    jal ra, at_eol
    mv s0, zero
    bnez a0, sk_if_open     # the condition is checked only if it is ever run,
    li s0, 1                # but there has to be one
sk_if_open:
    li a0, 1
    jal ra, blk_push
    bnez a0, sk_exit
    mv a0, s0
    j sk_exit

sk_endrepeat:
    la a0, buffer
    addi a0, a0, 9          # Skip "endrepeat"
    jal ra, at_eol
    bnez a0, sk_syntax
    jal ra, blk_top
    bnez a0, sk_loopmatch   # the innermost open construct has to be a loop
    jal ra, sk_depth
    mv s0, a0
    jal ra, blk_pop
    bnez s0, sk_none        # a loop opened inside the skipped text
    la t0, skip_kind        # the `repeat 0` body, or the abandoned loops, end here
    sw zero, 0(t0)
    jal ra, loops_settled
    j sk_none

sk_endif:
    la a0, buffer
    addi a0, a0, 5          # Skip "endif"
    jal ra, at_eol
    bnez a0, sk_syntax
    jal ra, blk_top
    li t0, 1
    bne a0, t0, sk_ifmatch  # the innermost open construct has to be an `if`
    jal ra, sk_depth
    mv s0, a0
    jal ra, blk_pop
    bnez s0, sk_none        # an `if` opened inside the skipped text
    la t0, skip_kind        # the `if` being skipped is over, whichever branch ran
    sw zero, 0(t0)
    la t0, if_depth
    lw t1, 0(t0)
    addi t1, t1, -1
    sw t1, 0(t0)
    j sk_none

# The one line a skip can stop at without its construct being over: a branch
# is still up for grabs, and this one may be the one that runs.
sk_else:
    jal ra, blk_top
    li t0, 1
    bne a0, t0, sk_ifmatch
    la a0, buffer
    addi a0, a0, 4          # Skip "else"
    jal ra, else_tail
    bnez a0, sk_exit
    mv s0, a2               # the condition, for an `else if`
    jal ra, blk_else_seen   # leaves a1, the plain-else flag, alone
    bnez a0, sk_exit
    jal ra, sk_depth
    bnez a0, sk_none        # belongs to an `if` opened inside the skipped text
    la t0, if_depth         # this is the `if` being decided
    lw t1, 0(t0)
    addi t1, t1, -1
    slli t1, t1, 2
    la t2, if_stack
    add t2, t2, t1
    lw t3, 0(t2)
    bnez t3, sk_none        # a branch already ran; keep skipping to endif
    bnez a1, sk_take        # a plain else always runs
    mv a0, s0
    jal ra, eval_cond
    bnez a0, sk_badcond
    beqz a1, sk_none
sk_take:
    li s0, 0
sk_mark:
    la t0, if_depth         # this branch runs, or, after a bad condition,
    lw t1, 0(t0)            # stands in for one so no later branch does
    addi t1, t1, -1
    slli t1, t1, 2
    la t2, if_stack
    add t2, t2, t1
    li t3, 1
    sw t3, 0(t2)
    bnez s0, sk_badexit
    la t0, skip_kind
    sw zero, 0(t0)
    j sk_none
sk_badcond:
    mv s0, a0
    j sk_mark
sk_badexit:
    mv a0, s0
    j sk_exit

sk_syntax:
    li a0, 1
    j sk_exit
sk_loopmatch:
    li a0, 12
    j sk_exit
sk_ifmatch:
    li a0, 14
    j sk_exit
sk_none:
    li a0, 0

sk_exit:
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

# a0 = how far the innermost open construct sits above the one the skip
# belongs to: 0 means it is that construct.
sk_depth:
    la t0, blk_depth
    lw t0, 0(t0)
    la t1, skip_base
    lw t1, 0(t1)
    sub a0, t0, t1
    ret
