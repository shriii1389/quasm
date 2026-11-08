.globl report_error

.data
    .align 2
    err_line_pre: .string "Line "
    err_line_post: .string ": "

.text
# a0 = the code a statement handler returned. Handlers unwind their own frames before returning, so this only prints and resumes the input loop.
report_error:
    mv t5, a0                  # the line-number prefix needs a0 for its ecalls
    la a0, err_line_pre
    li a7, 4
    ecall
    la t0, cur_line
    lw a0, 0(t0)
    li a7, 1                   # Syscall for integer output
    ecall
    la a0, err_line_post
    li a7, 4
    ecall
    mv a0, t5

    li t0, 2
    beq a0, t0, err_at_undeclared
    li t0, 3
    beq a0, t0, err_at_index
    li t0, 4
    beq a0, t0, err_at_size
    li t0, 5
    beq a0, t0, err_at_storage
    li t0, 6
    beq a0, t0, err_at_amps
    li t0, 7
    beq a0, t0, err_at_samebit
    li t0, 8
    beq a0, t0, err_at_samereg
    li t0, 9
    beq a0, t0, err_at_seed
    li t0, 10
    beq a0, t0, err_at_loopfull
    li t0, 11
    beq a0, t0, err_at_loopdeep
    li t0, 12
    beq a0, t0, err_at_loopmatch
    li t0, 13
    beq a0, t0, err_at_ifdeep
    li t0, 14
    beq a0, t0, err_at_ifmatch
    li t0, 15
    beq a0, t0, err_at_cvarfull
    li t0, 16
    beq a0, t0, err_at_noiserate
    li t0, 17
    beq a0, t0, err_at_range
    li t0, 18
    beq a0, t0, err_at_zeronorm
    li t0, 19
    beq a0, t0, err_at_elseelse
    li t0, 20
    beq a0, t0, err_at_toolong
    la a0, err_syntax          # code 1, and anything unrecognised
    j err_print

err_at_undeclared:
    la a0, err_undeclared
    j err_print
err_at_index:
    la a0, err_index
    j err_print
err_at_size:
    la a0, err_size
    j err_print
err_at_storage:
    la a0, err_storage
    j err_print
err_at_amps:
    la a0, err_amps
    j err_print
err_at_samebit:
    la a0, err_samebit
    j err_print
err_at_samereg:
    la a0, err_samereg
    j err_print
err_at_seed:
    la a0, err_seed
    j err_print
err_at_loopfull:
    la a0, err_loopfull
    j err_print
err_at_loopdeep:
    la a0, err_loopdeep
    j err_print
err_at_loopmatch:
    la a0, err_loopmatch
    j err_print
err_at_ifdeep:
    la a0, err_ifdeep
    j err_print
err_at_ifmatch:
    la a0, err_ifmatch
    j err_print
err_at_cvarfull:
    la a0, err_cvarfull
    j err_print
err_at_noiserate:
    la a0, err_noiserate
    j err_print
err_at_range:
    la a0, err_range
    j err_print
err_at_zeronorm:
    la a0, err_zeronorm
    j err_print
err_at_elseelse:
    la a0, err_elseelse
    j err_print
err_at_toolong:
    la a0, err_toolong

err_print:
    li a7, 4
    ecall
    jal ra, abort_loops        # an error breaks out of any enclosing loop
    j input_loop
