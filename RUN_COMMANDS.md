# ShukCar Run Commands

Все режимы теперь запускаются прямо на ПК и полностью на Python.

## 1. Основная desktop-версия

```powershell
.\.venv\Scripts\python.exe launcher.py desktop
```

или короче:

```powershell
.\desktop.cmd
```

или:

```powershell
.\main.cmd
```

## 2. Mobile-режим на ПК

Это отдельное узкое окно в стиле телефона, но тоже на Python/PyQt и тоже на компьютере.

```powershell
.\.venv\Scripts\python.exe launcher.py mobile
```

или короче:

```powershell
.\mobile.cmd
```

или:

```powershell
.\mobil.cmd
```

## 3. Desktop + Mobile одновременно

Сразу открываются два окна:
- обычная desktop-версия;
- отдельное mobile-окно.

```powershell
.\.venv\Scripts\python.exe launcher.py both
```

или короче:

```powershell
.\both.cmd
```
