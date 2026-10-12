## Téléchargement

| Système | Fichier |
|---|---|
| **macOS** (Apple Silicon : M1, M2, M3, M4…) | `MesFinances-macOS-AppleSilicon.zip` |
| **Windows** 10 / 11 | `MesFinances-Windows.exe` |

### Premier lancement

L'application n'est pas signée numériquement : votre système affichera un avertissement la première fois.

- **macOS** : décompressez le zip, glissez **Mes Finances** dans *Applications*, puis **clic droit → Ouvrir → Ouvrir**.
  Si macOS indique que l'application est « endommagée », ouvrez le Terminal et tapez :
  `xattr -cr "/Applications/Mes Finances.app"`
- **Windows** : si « Windows a protégé votre ordinateur » s'affiche, cliquez sur **Informations complémentaires → Exécuter quand même**.

Vos données restent sur votre ordinateur :
macOS `~/Library/Application Support/Mes Finances/finance.db` · Windows `%APPDATA%\Mes Finances\finance.db`
