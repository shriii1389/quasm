# name: end reached on a loop's second pass, which is replayed from the store
qubit q[1]
set c = 0
repeat 3
qubitop1 q[0] = X
print(q)
if c == 1
end
endif
set c = 1
endrepeat
print(q)
end
