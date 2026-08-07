/*
 * BOMI MQTT 계약 뷰어.
 *
 * AsyncAPI 3.0 문서를 표로 그린다. 라이브러리를 쓰지 않는 이유는 운영 Nginx 의
 * CSP 가 script-src 'self' 라 CDN 번들이 차단되고, 이 저장소에는 번들을 vendoring
 * 할 Node 빌드 단계가 없기 때문이다.
 *
 * 스펙 원본은 YAML 이며 백엔드가 JSON 으로 변환해 준다 (AsyncApiSpecController).
 */

(function () {
    'use strict';

    var SPEC_URL = '/openapi/bomi-mqtt.asyncapi.json';

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    /** #/components/... 를 따라간다. 외부 파일 참조는 이 스펙에 없다. */
    function deref(spec, node, seen) {
        seen = seen || 0;
        if (!node || typeof node !== 'object' || !node.$ref || seen > 20) return node;
        var path = node.$ref.replace(/^#\//, '').split('/');
        var target = spec;
        for (var i = 0; i < path.length; i++) {
            if (target == null) return node;
            target = target[decodeURIComponent(path[i].replace(/~1/g, '/').replace(/~0/g, '~'))];
        }
        return deref(spec, target, seen + 1);
    }

    /**
     * allOf 를 하나로 합친다. 뒤에 오는 조각이 앞을 덮어쓴다 — NavigateCommand 처럼
     * 공통 봉투를 상속하고 type/payload 만 좁히는 형태를 그대로 표현하기 위해서다.
     */
    function flatten(spec, schema) {
        schema = deref(spec, schema);
        if (!schema || typeof schema !== 'object') return {};
        if (!Array.isArray(schema.allOf)) return schema;

        var merged = { type: 'object', properties: {}, required: [] };

        // 자기 자신도 마지막 조각으로 합치되 allOf 는 떼고 넣는다. 그대로 넣으면
        // flatten 이 같은 노드로 다시 들어와 스택이 터진다.
        var own = {};
        Object.keys(schema).forEach(function (key) {
            if (key !== 'allOf') own[key] = schema[key];
        });
        var parts = schema.allOf.concat([own]);

        parts.forEach(function (raw) {
            var part = flatten(spec, raw);
            if (!part || typeof part !== 'object') return;
            Object.keys(part).forEach(function (key) {
                if (key === 'allOf') return;
                if (key === 'properties') {
                    Object.keys(part.properties || {}).forEach(function (name) {
                        merged.properties[name] = part.properties[name];
                    });
                } else if (key === 'required') {
                    (part.required || []).forEach(function (name) {
                        if (merged.required.indexOf(name) === -1) merged.required.push(name);
                    });
                } else {
                    merged[key] = part[key];
                }
            });
        });
        return merged;
    }

    function typeLabel(spec, schema) {
        var s = flatten(spec, schema);
        if (!s) return '';
        if (s.const !== undefined) return '"' + s.const + '"';
        var base = s.type || (s.properties ? 'object' : '');
        if (s.format) base += ' (' + s.format + ')';
        return base;
    }

    function constraintText(spec, schema) {
        var s = flatten(spec, schema);
        var bits = [];
        if (s.enum) bits.push(s.enum.join(' | '));
        if (s.const !== undefined) bits.push(String(s.const) + ' 고정');
        if (s.minimum !== undefined || s.maximum !== undefined) {
            bits.push(
                (s.minimum !== undefined ? s.minimum : '') +
                '~' +
                (s.maximum !== undefined ? s.maximum : '')
            );
        }
        if (s.maxLength !== undefined) bits.push('최대 ' + s.maxLength + '자');
        return bits.join(', ');
    }

    /** payload 는 한 겹 중첩돼 있어서 재귀로 편다. 접두어로 경로를 보여 준다. */
    function collectRows(spec, schema, prefix, rows, depth) {
        var s = flatten(spec, schema);
        if (!s || !s.properties || depth > 3) return rows;
        var required = s.required || [];

        Object.keys(s.properties).forEach(function (name) {
            var child = flatten(spec, s.properties[name]);
            var path = prefix ? prefix + '.' + name : name;
            rows.push({
                path: path,
                type: typeLabel(spec, s.properties[name]),
                required: required.indexOf(name) !== -1,
                constraint: constraintText(spec, s.properties[name]),
                description: (child && child.description) || ''
            });
            if (child && child.properties) {
                collectRows(spec, child, path, rows, depth + 1);
            }
        });
        return rows;
    }

    function fieldTable(spec, schema) {
        var rows = collectRows(spec, schema, '', [], 0);
        if (!rows.length) return null;

        var wrap = el('div', 'table-scroll');
        var table = el('table');
        var thead = el('thead');
        var hr = el('tr');
        ['필드', '타입', '필수', '제약', '설명'].forEach(function (h) {
            hr.appendChild(el('th', null, h));
        });
        thead.appendChild(hr);
        table.appendChild(thead);

        var tbody = el('tbody');
        rows.forEach(function (row) {
            var tr = el('tr');
            tr.appendChild(el('td', 'field', row.path));
            tr.appendChild(el('td', null, row.type));
            var req = el('td', 'req');
            req.appendChild(el('span', row.required ? 'yes' : 'no', row.required ? '예' : '—'));
            tr.appendChild(req);
            tr.appendChild(el('td', 'enum', row.constraint));
            tr.appendChild(el('td', null, row.description));
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        return wrap;
    }

    function renderMessage(spec, message) {
        message = deref(spec, message);
        var box = el('div', 'message');

        box.appendChild(el('h3', null, (message.name || '') + (message.title ? ' — ' + message.title : '')));
        if (message.summary) box.appendChild(el('p', 'prose', message.summary.trim()));

        var table = fieldTable(spec, message.payload);
        if (table) {
            box.appendChild(el('h4', null, '필드'));
            box.appendChild(table);
        }

        (message.examples || []).forEach(function (example) {
            box.appendChild(el('h4', null, '예시 — ' + (example.name || '')));
            box.appendChild(el('pre', null, JSON.stringify(example.payload, null, 2)));
        });

        return box;
    }

    /** 채널마다 어떤 operation 이 붙어 있는지 역인덱스를 만든다. */
    function operationsByChannel(spec) {
        var index = {};
        Object.keys(spec.operations || {}).forEach(function (key) {
            var op = spec.operations[key];
            var ref = op.channel && op.channel.$ref;
            if (!ref) return;
            var channelKey = ref.split('/').pop();
            (index[channelKey] = index[channelKey] || []).push(op);
        });
        return index;
    }

    function render(spec) {
        var root = document.getElementById('root');
        root.textContent = '';

        var info = spec.info || {};
        root.appendChild(el('h1', null, info.title || 'MQTT 계약'));
        root.appendChild(el('p', 'version', 'AsyncAPI ' + (spec.asyncapi || '') + ' · 버전 ' + (info.version || '')));
        if (info.description) root.appendChild(el('p', 'prose', info.description.trim()));

        var channels = spec.channels || {};
        var opIndex = operationsByChannel(spec);
        var channelKeys = Object.keys(channels);

        root.appendChild(el('h2', null, '토픽 목록'));
        var toc = el('ul', 'toc');
        channelKeys.forEach(function (key) {
            var li = el('li');
            var a = el('a', null, (channels[key].title || key) + ' — ' + channels[key].address);
            a.href = '#channel-' + key;
            li.appendChild(a);
            toc.appendChild(li);
        });
        root.appendChild(toc);

        channelKeys.forEach(function (key) {
            var channel = channels[key];
            var heading = el('h2', null, channel.title || key);
            heading.id = 'channel-' + key;
            root.appendChild(heading);

            (opIndex[key] || []).forEach(function (op) {
                var send = op.action === 'send';
                var badge = el(
                    'span',
                    'badge ' + (send ? 'badge-send' : 'badge-receive'),
                    send ? 'Backend 발행' : 'Backend 구독'
                );
                root.appendChild(badge);
            });

            root.appendChild(el('div', 'address', channel.address || ''));
            if (channel.description) root.appendChild(el('p', 'prose', channel.description.trim()));

            var params = channel.parameters || {};
            Object.keys(params).forEach(function (name) {
                root.appendChild(el('p', 'prose', '{' + name + '} — ' + (params[name].description || '')));
            });

            var messages = channel.messages || {};
            Object.keys(messages).forEach(function (name) {
                root.appendChild(renderMessage(spec, messages[name]));
            });
        });
    }

    fetch(SPEC_URL, { headers: { Accept: 'application/json' } })
        .then(function (response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
        })
        .then(render)
        .catch(function (error) {
            var root = document.getElementById('root');
            root.textContent = '';
            var p = el('p', 'error', '계약을 불러오지 못했습니다 (' + error.message + '). ');
            var a = el('a', null, 'AsyncAPI YAML 원본 열기');
            a.href = '/openapi/bomi-mqtt.asyncapi.yaml';
            p.appendChild(a);
            root.appendChild(p);
        });
})();
