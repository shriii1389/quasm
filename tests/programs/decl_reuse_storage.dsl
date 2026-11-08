# name: redeclaring at the same size reuses the block, so this cannot run out
qubit a[6]
repeat 40
qubit a[6]
qubitop1 a[0] = H
endrepeat
print(a)
end
