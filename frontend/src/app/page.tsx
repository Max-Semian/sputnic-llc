"use client";

import { useState } from "react";
import { Alert, Col, Container, Row } from "react-bootstrap";

import { AlertsTable } from "@/components/AlertsTable";
import { FilesTable } from "@/components/FilesTable";
import { PageHeader } from "@/components/PageHeader";
import { UploadFileModal } from "@/components/UploadFileModal";
import { useDashboardData } from "@/hooks/useDashboardData";

/**
 * Dashboard page. All data access and side effects are delegated to hooks and
 * API modules; this component only composes presentational components.
 */
export default function Page() {
  const { files, alerts, isLoading, error, loadData } = useDashboardData();
  const [showUpload, setShowUpload] = useState(false);

  return (
    <Container fluid className="py-4 px-4 bg-light min-vh-100">
      <Row className="justify-content-center">
        <Col xxl={10} xl={11}>
          <PageHeader
            onRefresh={() => void loadData()}
            onAddFile={() => setShowUpload(true)}
            isRefreshing={isLoading}
          />

          {error && (
            <Alert variant="danger" className="shadow-sm">
              {error}
            </Alert>
          )}

          <FilesTable files={files} isLoading={isLoading} />

          <Row>
            <Col>
              <AlertsTable alerts={alerts} isLoading={isLoading} />
            </Col>
          </Row>
        </Col>
      </Row>

      <UploadFileModal
        show={showUpload}
        onHide={() => setShowUpload(false)}
        onUploaded={() => void loadData()}
      />
    </Container>
  );
}
