# name: T then T-dagger is the identity, in both orders
qubit a = [(0.6,0.1),(0.3,-0.73484692)]
qubitop1 a[0] = T
qubitop1 a[0] = TDG
print(a)
qubitop1 a[0] = TDG
qubitop1 a[0] = T
print(a)
end
