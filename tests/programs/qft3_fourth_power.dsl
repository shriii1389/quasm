# name: the QFT has order four: QFT^4 = I on an asymmetric state
qubit q = [(-0.108256,0.172092),(0.147002,0.489224),(-0.034986,-0.191224),(-0.368518,0.361488),(-0.127970,-0.329797),(0.176057,0.046916),(-0.062281,-0.313580),(-0.039879,0.362360)]
print(q)
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
print(q)
end
