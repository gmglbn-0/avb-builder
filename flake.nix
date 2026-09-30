{
  description = "avb-builder: Automated EvolutionX OTA builder and signing server";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonEnv = pkgs.python312.withPackages (ps: with ps; [
          aiohttp
          requests
          pyyaml
          fastapi
          uvicorn
          jinja2
          python-multipart
        ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.curl
            pkgs.unzip
            pkgs.git
          ];
          shellHook = ''
            export PATH="$PWD/bin:$PATH"
          '';
        };
      }
    );
}
