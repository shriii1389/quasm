# name: digits and the underscore name registers too
qubit 7[1]
qubit _[2]
qubitop1 7[0] = X
qubitop2 _[0],_[1] = SW
print(7)
print(_)
end
