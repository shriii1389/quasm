# A loop that stops working once it gets the answer it wanted.
#
# Each iteration prepares a biased coin -- p(1) = 0.25 -- and measures it.
# The first iteration to see a 1 sets d, and every later iteration's `if`
# takes the empty branch instead. QuAsm has no `break`, but a classical flag
# and a conditional get the same effect: the loop still turns 12 times, and
# only the attempts up to the first success do any work.
#
# `set` is what makes this possible without measuring -- a classical variable
# the program controls itself. Names are one character: d for done, r for the
# result of the trial.
seed 4242
set d = 0

repeat 12
if d == 0
qubit q = [(0.8660254,0),(0.5,0)]   # p(1) = 0.25
measure q[0] -> r
if r == 1
set d = 1                           # stop trying on the next pass
endif
endif
endrepeat

qubit f[1]
if d == 1
qubitop1 f[0] = X                   # |1>: some attempt succeeded
endif
print(f)                            # |0> would mean twelve failures in a row
end
