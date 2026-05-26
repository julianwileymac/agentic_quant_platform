{{/*
Phase 5 §8.1 helpers. Keep these minimal — operators override
values.yaml; the templates focus on the Pod / Service shape.
*/}}

{{- define "aqp-mcp-tenant.fullname" -}}
{{- printf "aqp-%s-mcp-%s" .kind .Values.tenant_id | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aqp-mcp-tenant.labels" -}}
app.kubernetes.io/part-of: {{ .Values.labels.partOf }}
app.kubernetes.io/managed-by: {{ .Values.labels.managedBy }}
app.kubernetes.io/component: {{ .Values.labels.component }}
aqp.io/cell-id: {{ .Values.cell_id | quote }}
aqp.io/tenant-id: {{ .Values.tenant_id | quote }}
aqp.io/tier: {{ .Values.tier | quote }}
{{- end -}}

{{- define "aqp-mcp-tenant.selector" -}}
app: {{ include "aqp-mcp-tenant.fullname" . }}
{{- end -}}
