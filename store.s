.globl store_var
.globl alloc_var

.text
# a0 = name pointer, a1 = base address, a2 = qubit count.
# a0 = 0 on success, 5 if the symbol table is full.
store_var:
    la t0, symbol_table
    addi t2, t0, 984      # last entry that still leaves a zero terminator

store_loop:
    lw t1, 0(t0)          # Check if this slot is empty
    beqz t1, store_here   # If empty (0), use this slot
    addi t0, t0, 12       # Else try next slot
    blt t0, t2, store_loop
    li a0, 5
    ret

store_here:
    lb t1, 0(a0)          # Load first character of name
    sw t1, 0(t0)          # Store the name (like "a")
    sw a1, 4(t0)          # Store address where data will be
    sw a2, 8(t0)          # Store how many qubits live there
    li a0, 0
    ret

# a0 = name pointer, a1 = byte size, a2 = qubit count. 
# a0 = 0 and a1 = base address on success; a0 = 5 if either arena is exhausted.
alloc_var:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s5, 24(sp)
    sw s6, 20(sp)
    sw s7, 16(sp)
    sw s8, 12(sp)
    mv s7, a0             # name
    mv s5, a1             # byte size
    mv s6, a2             # qubit count

    mv a0, s7
    jal ra, find_var
    beqz a0, alloc_new
    li t0, 8              # a k-qubit register occupies 8 * 2^k bytes
    sll t0, t0, a2
    blt t0, s5, alloc_grow
    sw s6, 8(a3)          # same block, new qubit count; a1 is still its base
    li a0, 0
    j alloc_exit

alloc_grow:
    mv s8, a3             # the entry to rebind once there is room
    jal ra, alloc_room
    bnez a0, alloc_exit
    sw a1, 4(s8)
    sw s6, 8(s8)
    li a0, 0
    j alloc_exit

alloc_new:
    jal ra, alloc_room
    bnez a0, alloc_exit
    mv s8, a1
    mv a0, s7
    mv a1, s8
    mv a2, s6
    jal ra, store_var
    bnez a0, alloc_exit   # symbol table full; a0 already holds the code
    mv a1, s8
    li a0, 0

alloc_exit:
    lw s8, 12(sp)
    lw s7, 16(sp)
    lw s6, 20(sp)
    lw s5, 24(sp)
    lw ra, 28(sp)
    addi sp, sp, 32
    ret

# Takes s5 bytes off the top of the arena. 
# a0 = 0 and a1 = base address; a0 = 5 if that would run past the end.
alloc_room:
    la t0, value_storage
    li t1, 4096           # arena size; too large for an addi immediate
    add t0, t0, t1        # one past the end of the arena
    add t1, s11, s5
    bgt t1, t0, alloc_room_full
    mv a1, s11
    mv s11, t1
    li a0, 0
    ret
alloc_room_full:
    li a0, 5
    ret
