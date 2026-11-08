# name: end inside a taken branch stops the program there
qubit q[1]
set c = 1
qubitop1 q[0] = H
print(q)
if c == 1
end
endif
print(q)
end
