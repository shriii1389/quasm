.data
    .align 2    # Align data to word boundaries.

    # Keywords
    qubit_str: .string "qubit "         # qubit declaration.
    print_str: .string "print"          # print statement.
    gate1_str: .string "qubitop1"       # single-qubit gate operations.
    gate2_str: .string "qubitop2"       # two-qubit gate operations.
    measure_str: .string "measure"      # measurement and collapse.
    seed_str: .string "seed"            # reseeds the measurement PRNG.
    end_str: .string "end"              # program termination.

    # Error messages
    err_syntax: .string "Syntax Error\n"
    err_undeclared: .string "Variable not declared\n"
    err_index: .string "Qubit index out of range\n"
    err_size: .string "Register size out of range (1 to 6 qubits)\n"
    err_storage: .string "Out of qubit storage\n"
    err_amps: .string "Amplitude count must be a power of two\n"
    err_samebit: .string "Two-qubit gate needs two distinct qubits\n"
    err_samereg: .string "Two-qubit gate operands must be one register\n"
    err_seed: .string "Seed must be nonzero\n"
    err_loopfull: .string "Loop body too long\n"
    err_loopdeep: .string "Loops nested more than 8 deep\n"
    err_loopmatch: .string "endrepeat without repeat\n"
    err_ifdeep: .string "Conditionals nested more than 8 deep\n"
    err_ifmatch: .string "else or endif without if\n"
    err_cvarfull: .string "Out of classical variable storage\n"
    err_noiserate: .string "Noise rate must be between 0 and 1\n"
    err_range: .string "Number out of range\n"
    err_zeronorm: .string "Cannot measure a register with zero norm\n"
    err_elseelse: .string "else after else\n"
    err_toolong: .string "Line too long\n"

    .align 2
    # Single-qubit gates, row-major with each entry as (re, im) pair.
    Hgate: .float 0.70710678,0, 0.70710678,0
           .float 0.70710678,0, -0.70710678,0
    Igate: .float 1,0, 0,0
           .float 0,0, 1,0
    Xgate: .float 0,0, 1,0
           .float 1,0, 0,0
    Ygate: .float 0,0, 0,-1
           .float 0,1, 0,0
    Zgate: .float 1,0, 0,0
           .float 0,0, -1,0
    Sgate: .float 1,0, 0,0
           .float 0,0, 0,1
    Tgate: .float 1,0, 0,0
           .float 0,0, 0.70710678,0.70710678
    
    SNgate: .float 0.5,0.5, 0.5,-0.5
            .float 0.5,-0.5, 0.5,0.5
    # The inverses of S and T, which Clifford+T circuits such as the Toffoli decomposition need.
    SDGgate: .float 1,0, 0,0
             .float 0,0, 0,-1
    TDGgate: .float 1,0, 0,0
             .float 0,0, 0.70710678,-0.70710678

    # Two-qubit gates, one 4x4 each, row-major indexed as |control target>.
    CNgate: .float 1,0, 0,0, 0,0, 0,0
            .float 0,0, 1,0, 0,0, 0,0
            .float 0,0, 0,0, 0,0, 1,0
            .float 0,0, 0,0, 1,0, 0,0
    SWgate: .float 1,0, 0,0, 0,0, 0,0
            .float 0,0, 0,0, 1,0, 0,0
            .float 0,0, 1,0, 0,0, 0,0
            .float 0,0, 0,0, 0,0, 1,0
    CYgate: .float 1,0, 0,0, 0,0, 0,0
            .float 0,0, 1,0, 0,0, 0,0
            .float 0,0, 0,0, 0,0, 0,-1
            .float 0,0, 0,0, 0,1, 0,0
    CZgate: .float 1,0, 0,0, 0,0, 0,0
            .float 0,0, 1,0, 0,0, 0,0
            .float 0,0, 0,0, 1,0, 0,0
            .float 0,0, 0,0, 0,0, -1,0

    CP1gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, -1,0
    CP2gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, 0,1
    CP3gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, 0.70710678,0.70710678
    CP4gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, 0.92387953,0.38268343
    CP5gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, 0.98078528,0.19509032
    CP6gate: .float 1,0, 0,0, 0,0, 0,0
             .float 0,0, 1,0, 0,0, 0,0
             .float 0,0, 0,0, 1,0, 0,0
             .float 0,0, 0,0, 0,0, 0.99518473,0.09801714

    # Scratch for apply_gate2: the four amplitudes a group touches, their addresses, and the four results before they are written back.
    g2_addr: .word 0,0,0,0
    g2_amp: .float 0,0,0,0,0,0,0,0
    g2_tmp: .float 0,0,0,0,0,0,0,0

    # Symbol table: 12-byte entries of (name char, base address, qubit count), 
    # Terminated by a zero name. 1000 bytes holds 82 variables,
    # the last slot being reserved for the terminator.
    symbol_table: .space 1000
    # Amplitude storage, bump-allocated. An n-qubit register costs 2^n * 8
    # bytes, so the 6-qubit cap is 512 bytes and this arena holds eight
    # maximum-size registers. The cap keeps a declaration from ever
    # outgrowing the arena in one step; alloc_var enforces the arena bound.
    value_storage: .space 4096
    # Input buffer for user commands. 1024 bytes holds a 6-qubit register's
    # explicit amplitude list; next_line rejects any line that does not fit.
    buffer: .space 1024
    .align 2
    prompt: .string ">> "       # Prompt string for user input.
    .align 2
    newline: .string "\n"

.text
.globl main
main:
    # Initialize memory pointers
    la s11, value_storage  # Bump pointer into the amplitude arena.
    la t0, prog_store      # Bump pointer into the loop-body store.
    la t1, prog_end
    sw t0, 0(t1)

    input_loop:
        # Statements come from stdin, or from the loop store while a `repeat`
        # is replaying its body.
        jal ra, next_line
        bnez a0, report_error

        la a0, buffer      # Blank lines and # comments are not statements.
        jal ra, at_eol
        beqz a0, input_loop

        la t0, skip_kind   # In a `repeat 0` body, an untaken `if` branch or
        lw t0, 0(t0)       # after an inner `end`, read the lines but run none.
        beqz t0, check_1Qubitgate_op
        jal ra, skip_line
        beqz a0, input_loop
        j report_error

        # Every handler returns 0 on success or an error code in a0, having
        # already unwound its own frame, so failures never strand the stack.
        check_1Qubitgate_op:
            la t0, buffer               # Load input into temporary register.
            la t1, gate1_str            # Load single-qubit gate keyword.
            jal starts_with             # Check if input starts with this keyword.
            bnez a0, check_2Qubitgate_op   # If not, move to two-qubit gate check.

            jal ra, handle_qubitop1_stmt
            beqz a0, input_loop
            j report_error

        check_2Qubitgate_op:
            la t0, buffer
            la t1, gate2_str            # Load two-qubit gate keyword.
            jal starts_with
            bnez a0, check_print_op

            jal ra, handle_qubitop2_stmt
            beqz a0, input_loop
            j report_error

        check_print_op:
            la t0, buffer
            la t1, print_str
            jal check_print_cmd
            bnez a0, check_qubit_decl

            jal ra, handle_print_stmt
            beqz a0, input_loop
            j report_error

        check_qubit_decl:
            la t0, buffer               # Example: qubit a = [(1,0),(0,1)]
            la t1, qubit_str            # Check for qubit declarations.
            jal starts_with
            bnez a0, check_measure_op

            jal ra, handle_qubit_decl
            beqz a0, input_loop
            j report_error

        check_measure_op:
            la t0, buffer
            la t1, measure_str          # Check for measurement statements.
            jal starts_with
            bnez a0, check_seed_op

            jal ra, handle_measure_stmt
            beqz a0, input_loop
            j report_error

        check_seed_op:
            la t0, buffer
            la t1, seed_str
            jal starts_with
            bnez a0, check_noise_op

            jal ra, handle_seed_stmt
            beqz a0, input_loop
            j report_error

        check_noise_op:
            la t0, buffer
            la t1, noise_str            # Check for the depolarising rate.
            jal starts_with
            bnez a0, check_set_op

            jal ra, handle_noise_stmt
            beqz a0, input_loop
            j report_error

        check_set_op:
            la t0, buffer
            la t1, set_str              # Check for classical assignments.
            jal starts_with
            bnez a0, check_repeat_op

            jal ra, handle_set_stmt
            beqz a0, input_loop
            j report_error

        check_repeat_op:
            la t0, buffer
            la t1, repeat_str           # Check for the head of a loop.
            jal token_eq
            bnez a0, check_endrepeat_op

            jal ra, handle_repeat_stmt
            beqz a0, input_loop
            j report_error

        check_endrepeat_op:
            la t0, buffer               # Before "end", which is a prefix of it.
            la t1, endrepeat_str
            jal token_eq
            bnez a0, check_if_op

            jal ra, handle_endrepeat_stmt
            beqz a0, input_loop
            j report_error

        check_if_op:
            la t0, buffer               # Check for the head of a conditional.
            la t1, if_str
            jal token_eq
            bnez a0, check_else_op

            jal ra, handle_if_stmt
            beqz a0, input_loop
            j report_error

        check_else_op:
            la t0, buffer               # "else", or "else if <cond>".
            la t1, else_str
            jal token_eq
            bnez a0, check_endif_op

            jal ra, handle_else_stmt
            beqz a0, input_loop
            j report_error

        check_endif_op:
            la t0, buffer               # Before "end", a prefix of it too.
            la t1, endif_str
            jal token_eq
            bnez a0, check_end_cmd

            jal ra, handle_endif_stmt
            beqz a0, input_loop
            j report_error

        check_end_cmd:
            la t0, buffer
            la t1, end_str              # Check for "end" keyword to terminate.
            jal token_eq
            bnez a0, syntax_fallthrough
            la a0, buffer
            addi a0, a0, 3              # Skip "end"
            jal ra, at_eol              # `end` takes nothing after it
            bnez a0, syntax_fallthrough

            jal ra, handle_end_stmt     # returns only if blocks are still open
            j input_loop

        # Fall-through case: Syntax error if no command matches.
        syntax_fallthrough:
        li a0, 1
        j report_error

# Data related code files
.include "store.s"         # variable storage functions.
.include "search.s"        # symbol table search functions.

# Miscellenious code files
.include "errors.s"        # error handling.
.include "utils.s"         # utility functions.
.include "gateFunctions.s" # the statevector gate kernel.

# keywords related code files
.include "print.s"         # handling print statements.
.include "qubit.s"         # qubit-specific operations.
.include "oneQubitGate.s"  # single-qubit gate operations.
.include "twoQubitGate.s"  # two-qubit gate operations.
.include "measure.s"       # measurement and the PRNG.
.include "cond.s"          # classical values and `if`.
.include "noise.s"         # the depolarising channel.
.include "script.s"        # the line source and loops.
