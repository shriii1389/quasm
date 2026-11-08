# name: an if needs a condition even where it is never evaluated
# expect_error: Syntax Error
set c = 1
if c == 0
if
endif
endif
end
