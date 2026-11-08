# name: nested loops multiply, 2 x 3 = 6 X gates
qubit a[1]
repeat 2
repeat 3
qubitop1 a[0] = X
endrepeat
print(a)
endrepeat
end
