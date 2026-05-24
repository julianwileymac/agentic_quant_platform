# Upstream Theia IDE README (archived)

Status: `archive`.

The file below is the original `README.md` shipped by the upstream
Eclipse Theia IDE workspace (`eclipse-theia/theia-ide`) at the commit
this `aqp_ide/` folder was vendored from. Preserved for licence
attribution and as a reference for the upstream build commands.

The canonical AQP-flavoured README is at [`../../README.md`](../../README.md).

---

<br/>
<div id="theia-logo" align="center">
    <br />
    <img src="https://raw.githubusercontent.com/eclipse-theia/theia-ide/master/theia-extensions/product/src/browser/icons/TheiaIDE.png" alt="Theia Logo" width="300"/>
    <h3>Eclipse Theia IDE</h3>
</div>

The Eclipse Theia IDE is built with this project. Eclipse Theia IDE also
serves as a template for building desktop-based products based on the
Eclipse Theia platform.

## License

- [MIT](LICENSE)

## Trademark

"Theia" is a trademark of the Eclipse Foundation
<https://www.eclipse.org/theia>

## What is this?

The Eclipse Theia IDE is a modern and open IDE for cloud and desktop.
The Theia IDE is based on the [Theia platform](https://theia-ide.org).

The Eclipse Theia IDE also serves as a **template** for building
desktop-based products based on the Eclipse Theia platform, as well as
to showcase Eclipse Theia capabilities.

## Theia IDE vs Theia Blueprint

The Theia IDE has been rebranded from its original name "Theia
Blueprint". You can therefore assume the terms "Theia IDE" and "Theia
Blueprint" to be synonymous.

## Development

### Requirements

Please check Theia's [prerequisites](https://github.com/eclipse-theia/theia/blob/master/doc/Developing.md#prerequisites),
and keep node versions aligned between Theia IDE and that of the
referenced Theia version.

### Repository Structure

- Root level configures mono-repo build with lerna
- `applications` groups the different app targets
  - `browser` contains a browser based version of Eclipse Theia IDE
    that may be packaged as a Docker image
  - `electron` contains the electron app to package, packaging
    configuration, and E2E tests for the electron target.
- `theia-extensions` groups the various custom theia extensions for the
  Eclipse Theia IDE
- `patches` contains patches applied to upstream packages

### Build

```sh
# Dev build
yarn && yarn build:dev && yarn download:plugins

# Production build
yarn && yarn build && yarn download:plugins
```

### Running Browser app

```sh
yarn browser start
```

and connect to <http://localhost:3000/>

### Docker

```sh
docker build -t theia-ide -f browser.Dockerfile .
docker run -p=3000:3000 --rm theia-ide
```

and connect to <http://localhost:3000/>
