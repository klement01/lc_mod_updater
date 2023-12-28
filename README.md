# Lethal Company Mod Updater

Takes a file containing URLs for Lethal Company mods in [Thunderstore](https://thunderstore.io/c/lethal-company/), finds all their dependencies, downloads them and extracts them in the correct file tree. The resulting folder can be moved to the game installation folder and distributed. Example usage:

```shell
python .\updater.py .\mod_list.txt
```

It can also be used to export a formatted modlist with the ```-e``` command line argument, which include the mod name downloaded from the repository.

When running, the tool shows how long ago each mod has been updated, which can be used to check for compatibility with recent versions. A timeline of patches can be viewed on the [Lethal Company SteamDB patches page](https://steamdb.info/app/1966720/patchnotes/).

The repository also includes a mod list used by me.

# Installing a modpack

Once a modpack has been created in a folder named with the format ```LC_modpack_YYYY-mm-dd_HH-MM-SS```, install it by moving its contents into the Lethal Company folder. To ensure no old mods are left installed, delete the ```BepInEx``` inside the game's directory before installing a new modpack, if it is present.