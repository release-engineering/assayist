# SPDX-License-Identifier: GPL-3.0+

from assayist.client import query
from assayist.common.models.content import Build, Artifact
from assayist.common.models.source import SourceLocation


def test_get_container_sources():
    """Test the get_container_sources function."""
    # Create the container build entry
    container_build_id = '742663'
    container_build = Build(id_=container_build_id, type_='container').save()
    container_filename = ('docker-image-sha256:98217b7c89052267e1ed02a41217c2e03577b96125e923e9594'
                          '1ac010f209ee6.x86_64.tar.gz')
    container_artifact = Artifact(
        archive_id='742663',
        rpm_id='0',
        architecture='x86_64',
        filename=container_filename,
        type_='container').save()
    container_build.artifacts.connect(container_artifact)
    container_internal_url = ('git://pks.domain.local/containers/etcd#'
                              '3dcd6fc75e674589ac7d2294dbf79bd8ebd459fb')
    container_internal_source = SourceLocation(url=container_internal_url).save()
    container_build.source_location.connect(container_internal_source)

    # Create the embedded artifacts
    etcd_build = Build(id_='770188', type_='rpm').save()
    etcd_rpm = Artifact(
        archive_id='0',
        rpm_id='5818103',
        architecture='x86_64',
        filename='etcd-3.2.22-1.el7.x86_64.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_rpm)
    etcd_upstream_url = ('https://github.com/coreos/etcd/archive/1674e682fe9fbecd66e9f20b77da852ad7'
                         'f517a9/etcd-1674e682.tar.gz')
    etcd_upstream_source = SourceLocation(url=etcd_upstream_url).save()
    etcd_internal_url = 'git://pks.domain.local/rpms/etcd#84858fb38a89e1177b0303c675d206f90f6a83e2'
    etcd_internal_source = SourceLocation(url=etcd_internal_url).save()
    etcd_build.source_location.connect(etcd_internal_source)
    etcd_internal_source.upstream.connect(etcd_upstream_source)
    container_artifact.embedded_artifacts.connect(etcd_rpm)

    yum_utils_build = Build(id_='728353', type_='rpm').save()
    yum_utils_rpm = Artifact(
        archive_id='0',
        rpm_id='5962202',
        architecture='x86_64',
        type_='rpm',
        filename='yum-utils-1.1.31-46.el7_5.noarch.rpm').save()
    yum_utils_build.artifacts.connect(yum_utils_rpm)
    yum_utils_upstream_url = 'http://yum.baseurl.org/download/yum-utils/yum-utils-1.1.31.tar.gz'
    yum_utils_upstream_source = SourceLocation(url=yum_utils_upstream_url).save()
    yum_utils_internal_url = ('git://pks.domain.local/rpms/yum-utils#562e476db1be88f58662d6eb3'
                              '82bb37e87bf5824')
    yum_utils_internal_source = SourceLocation(url=yum_utils_internal_url).save()
    yum_utils_build.source_location.connect(yum_utils_internal_source)
    yum_utils_internal_source.upstream.connect(yum_utils_upstream_source)
    container_artifact.embedded_artifacts.connect(yum_utils_rpm)

    expected = {
        'internal_urls': [yum_utils_internal_url, etcd_internal_url],
        'upstream_urls': [yum_utils_upstream_url, etcd_upstream_url]
    }
    assert query.get_container_content_sources(container_build_id) == expected
