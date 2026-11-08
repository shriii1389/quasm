# name: two loops in a row, the second shorter than the first
qubit a[1]
repeat 2
qubitop1 a[0] = X
qubitop1 a[0] = I
qubitop1 a[0] = I
endrepeat
print(a)
repeat 3
qubitop1 a[0] = X
endrepeat
print(a)
end
