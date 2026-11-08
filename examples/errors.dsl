# Mistakes on purpose. Each bad line is reported with its line number and
# skipped; the interpreter carries on, so the good lines still run.
qubit q[2]
qubitop1 q[0] = H
qubitop1 q[5] = X              # only q[0] and q[1] exist
qubitop2 q[0],q[0] = CN        # control and target must differ
qubitop1 q[1] = Q              # there is no gate Q
measure r[0]                   # r was never declared
set c = 99999999999            # too wide for a 32-bit integer
print(q)                       # only the H on q[0] took effect
end
