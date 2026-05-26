{{/*
Phase 6 §9 helpers. Keep these minimal — operators override
values.yaml; the templates focus on per-cell datastore shapes.
*/}}

{{- define "aqp-cell-data-plane.bucketPrefix" -}}
{{- if .Values.minio.bucketPrefix -}}
{{- .Values.minio.bucketPrefix -}}
{{- else -}}
aqp-{{ .Values.cell_id }}
{{- end -}}
{{- end -}}

{{- define "aqp-cell-data-plane.labels" -}}
app.kubernetes.io/part-of: {{ .Values.labels.partOf }}
app.kubernetes.io/managed-by: {{ .Values.labels.managedBy }}
app.kubernetes.io/component: {{ .Values.labels.component }}
aqp.io/cell-id: {{ .Values.cell_id | quote }}
aqp.io/cell-tier: {{ .Values.tier | quote }}
aqp.io/cell-region: {{ .Values.region | quote }}
{{- end -}}

{{- define "aqp-cell-data-plane.podAnnotations" -}}
linkerd.io/inject: {{ .Values.linkerdInject | quote }}
{{- end -}}
