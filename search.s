.globl find_var
.globl next_var
.globl not_found

.text
# a0 = pointer to a variable name (only its first character is significant).
# On success: a0 = 1, a1 = base address, a2 = qubit count, a3 = the symbol table entry itself
# a0 = 0 on failure.
find_var:
    la t0, symbol_table
    lb t1, 0(a0)          # Get first char of name we're looking for

find_loop:
    lw t2, 0(t0)          # Load stored name
    beqz t2, not_found    # If empty slot, we didn't find it

    bne t1, t2, next_var  # Compare first chars

    # Found it!
    lw a1, 4(t0)          # Get the storage address
    lw a2, 8(t0)          # Get the qubit count
    mv a3, t0             # Hand back the entry for in-place rebinding
    li a0, 1              # Return success
    ret

next_var:
    addi t0, t0, 12       # Entries are (name, address, qubit count)
    j find_loop

not_found:
    li a0, 0              # Return failure
    ret
