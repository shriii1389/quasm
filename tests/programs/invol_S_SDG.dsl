# name: S then S-dagger is the identity, in both orders
qubit a = [(0.6,0.1),(0.3,-0.73484692)]
qubitop1 a[0] = S
qubitop1 a[0] = SDG
print(a)
qubitop1 a[0] = SDG
qubitop1 a[0] = S
print(a)
end
