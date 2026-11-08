# redeclaring a name replaces it, size included
qubit a[1]
qubitop1 a[0] = X
qubit a[2]
print(a)
end
