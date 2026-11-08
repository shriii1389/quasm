# name: a malformed loop head inside a skipped branch is still an error
# expect_error: Syntax Error
set c = 1
if c == 0
repeat abc
endrepeat
endif
end
