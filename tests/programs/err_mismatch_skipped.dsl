# name: a mismatched closer inside a skipped branch is still an error
# expect_error: endrepeat without repeat
set c = 1
if c == 0
endrepeat
endif
end
