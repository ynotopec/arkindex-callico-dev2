#!/bin/sh -e
# Build and publish a Docker image.
# Requires CI_PROJECT_DIR and CI_REGISTRY_IMAGE to be set.
# VERSION defaults to latest.
# Will only push an image if the commit is on the master branch or if a tag is defined.
# Will automatically login to a registry if CI_REGISTRY, CI_REGISTRY_USER and CI_REGISTRY_PASSWORD are set.

if [ -z "$VERSION" ]; then
    VERSION=${CI_COMMIT_TAG:-latest}
fi

if [ -z "$VERSION" -o -z "$CI_PROJECT_DIR" -o -z "$CI_REGISTRY_IMAGE" ]; then
    echo Missing environment variables to build the image…
    exit 1
fi

docker build $CI_PROJECT_DIR -t "$CI_REGISTRY_IMAGE:$VERSION" -t "$CI_REGISTRY_IMAGE:commit-$CI_COMMIT_SHORT_SHA"

# Publish the image with commit tag for dev
echo $CI_REGISTRY_PASSWORD | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
docker push "$CI_REGISTRY_IMAGE:commit-$CI_COMMIT_SHORT_SHA"

# Publish the image on the master branch or on a tag
if [ "$CI_COMMIT_REF_NAME" = "master" -o -n "$CI_COMMIT_TAG" ]; then
  if [ -n "$CI_REGISTRY" -a -n "$CI_REGISTRY_USER" -a -n "$CI_REGISTRY_PASSWORD" ]; then
    docker push "$CI_REGISTRY_IMAGE:$VERSION"
  else
    echo "Missing environment variables to log in to the container registry…"
  fi
else
  echo "The build was not published to the repository registry (only for master branch or tags)…"
fi
