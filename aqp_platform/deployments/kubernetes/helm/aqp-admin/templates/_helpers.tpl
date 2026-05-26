{{/* Standard chart helpers — adapted from the official `helm create` defaults. */}}

{{- define "aqp-admin.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aqp-admin.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "aqp-admin.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aqp-admin.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aqp-admin.labels" -}}
app.kubernetes.io/name: {{ include "aqp-admin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ include "aqp-admin.chart" . }}
aqp.io/env: {{ .Values.global.env | quote }}
aqp.io/cluster: {{ .Values.global.cluster | quote }}
{{- end -}}

{{- define "aqp-admin.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aqp-admin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
