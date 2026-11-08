# name: Toffoli on a state with every amplitude distinct swaps exactly |110> and |111>
qubit t = [(-0.276399,-0.093278),(0.083838,-0.078728),(-0.660861,0.250940),(0.486420,0.179372),(0.222443,-0.022348),(-0.101777,-0.029788),(-0.108713,0.056079),(0.105885,-0.213982)]
qubitop1 t[2] = H
qubitop2 t[1],t[2] = CN
qubitop1 t[2] = TDG
qubitop2 t[0],t[2] = CN
qubitop1 t[2] = T
qubitop2 t[1],t[2] = CN
qubitop1 t[2] = TDG
qubitop2 t[0],t[2] = CN
qubitop1 t[1] = T
qubitop1 t[2] = T
qubitop1 t[2] = H
qubitop2 t[0],t[1] = CN
qubitop1 t[0] = T
qubitop1 t[1] = TDG
qubitop2 t[0],t[1] = CN
print(t)
end
