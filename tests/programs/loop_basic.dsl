# name: repeat runs its body exactly n times
qubit a[1]
repeat 3
qubitop1 a[0] = X
endrepeat
print(a)
end
