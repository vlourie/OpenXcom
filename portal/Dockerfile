# The portal site. Built from the portal/ folder:
#   docker build -t xp-portal .
# global.json is left out on purpose: the image brings its own SDK of the same major version.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props ./
COPY src/Xp.Manifest/Xp.Manifest.csproj src/Xp.Manifest/
COPY src/Xp.Launcher.Core/Xp.Launcher.Core.csproj src/Xp.Launcher.Core/
COPY src/Xp.Portal/Xp.Portal.csproj src/Xp.Portal/
RUN dotnet restore src/Xp.Portal/Xp.Portal.csproj
COPY src/Xp.Manifest/ src/Xp.Manifest/
COPY src/Xp.Launcher.Core/ src/Xp.Launcher.Core/
COPY src/Xp.Portal/ src/Xp.Portal/
RUN dotnet publish src/Xp.Portal/Xp.Portal.csproj -c Release -o /out --no-restore -p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /out .
# uploads and the data-protection keys live on volumes, owned by the unprivileged user
RUN mkdir -p /data/files /data/keys && chown -R app:app /data
USER app
ENV ASPNETCORE_ENVIRONMENT=Production \
    ASPNETCORE_HTTP_PORTS=8080 \
    Attachments__StorageRoot=/data/files \
    DataProtection__KeysDir=/data/keys
EXPOSE 8080
ENTRYPOINT ["dotnet", "Xp.Portal.dll"]
