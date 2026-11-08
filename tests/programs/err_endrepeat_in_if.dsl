# name: an endrepeat cannot close a loop while an if inside it is open
# expect_error: endrepeat without repeat
set c = 0
repeat 2
if c == 0
endrepeat
endif
endrepeat
end
