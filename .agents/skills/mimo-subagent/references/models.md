# MiMo model notes

## Default choice
Use `mimo/mimo-auto` by default.

Why:
- it is the most forgiving default for day-to-day delegation
- it may stay available even when a direct fixed model route has billing issues
- it avoids overfitting the skill to one exact backend

## Use an explicit model when
- the user names a model directly
- the user is comparing models
- a task must be reproduced on a specific model family

## Known useful commands
```powershell
mimo models mimo
mimo providers whoami
mimo run -m "mimo/mimo-auto" "Your task here"
```

## Windows fallback
If `mimo` is not resolved by the shell, use:

```powershell
C:\Users\misha\AppData\Roaming\npm\mimo.cmd
```
