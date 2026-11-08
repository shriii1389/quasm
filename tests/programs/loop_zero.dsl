# name: repeat 0 reads the body and runs none of it
qubit a[1]
repeat 0
qubitop1 a[0] = X
print(a)
endrepeat
print(a)
end
