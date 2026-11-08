# name: whitespace inside brackets is optional, as the language says
qubit q[ 3 ]
qubitop1 q[ 0 ] = H
qubitop2 q[ 0 ] , q[ 2 ] = CN
qubitop1 q [1] = X
print( q )
measure q[ 1 ] -> c
print(q)
end
