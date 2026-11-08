# 20 fair coin flips. H turns either collapsed outcome back into an even
# superposition, so one register is reprepared over and over.
seed 12345
qubit q[1]

repeat 20
qubitop1 q[0] = H
measure q[0]
endrepeat
end
