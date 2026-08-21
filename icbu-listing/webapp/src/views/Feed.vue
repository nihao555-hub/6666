<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>投料</h2>
        <p class="muted">先选一条路上品。做到一半关掉也能回来接着做，多条可以同时记着。</p>
      </div>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先登录一个店铺"
      description="登录之后才能按这家店的规则成稿、把图传到店铺图库。"
      style="margin-bottom: 14px"
    />

    <template v-if="!sessionId">
      <div class="chooser">
        <h3>先选一种上品方式</h3>
        <p class="muted">三条路：有实拍、平台画图不用先选类目；批量上品必须先选叶子类目。</p>
        <div class="path-grid path-grid-3">
          <button class="path-card" @click="startPath('photo')">
            <small>默认走这条</small>
            <b>有实拍</b>
            <p class="muted">手机或工厂已经拍好了。上传图，再填单价和起订量。AI 看图定类目。</p>
          </button>
          <button class="path-card" @click="startPath('ai')">
            <small>一张实拍都没有</small>
            <b>平台画图</b>
            <p class="muted">单条上品：写品名，平台画 6 张再填价。生成图会标黄，不是实拍。</p>
          </button>
          <button class="path-card" @click="startPath('doc')">
            <small>报价单 / 表格 / 目录</small>
            <b>批量上品</b>
            <p class="muted">先选类目，上传资料或表格，AI 填好商品表，前台改完再批量成稿。</p>
          </button>
        </div>
      </div>
      <div v-if="openSessions.length" class="resume-box">
        <h3>做到一半的</h3>
        <p class="muted">关掉页面或中途退出都还在。点一条接着做，可以同时记多条。</p>
        <div class="resume-list">
          <div v-for="item in openSessions" :key="item.id" class="resume-row">
            <button class="resume-card" @click="resumeSession(item.id)">
              <b>{{ item.title }}</b>
              <span class="muted">{{ item.path_label }} · 停在「{{ item.step_label }}」</span>
            </button>
            <el-button text @click="dropSession(item.id)">不要了</el-button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="flow-bar">
        <el-button @click="backToChooser">回选路</el-button>
        <span class="muted">{{ currentTitle }} · 做到一半会自动记下，关掉也能回来</span>
        <el-button text @click="dropCurrent">不要这条了</el-button>
      </div>

    <!-- 有实拍 -->
    <template v-if="tab === 'single'">
      <FishboneSteps v-model="photoStep" :steps="photoSteps" :reached="photoReached" />

      <div v-if="photoStep === 0" class="step-panel">
        <h3>上传产品图</h3>
        <p class="muted">单条最多 6 张。批量时按货号命名，例如 SKU-1001_1.jpg，会自动归成同一个商品。</p>
        <div class="toolbar" style="margin-top: 14px">
          <el-radio-group v-model="photoMode">
            <el-radio-button value="single">单条</el-radio-button>
            <el-radio-button value="batch">按货号批量</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="photoMode === 'single'" class="toolbar" style="margin-top: 10px">
          <el-radio-group v-model="photoSource">
            <el-radio-button value="upload">本地上传</el-radio-button>
            <el-radio-button value="photobank">图片银行</el-radio-button>
          </el-radio-group>
        </div>
        <el-upload
          v-if="photoMode === 'single' && photoSource === 'upload'"
          v-model:file-list="files"
          list-type="picture-card"
          :auto-upload="false"
          :limit="6"
          accept="image/*"
        >
          <span style="font-size: 22px">+</span>
        </el-upload>
        <div v-else-if="photoMode === 'single' && photoSource === 'photobank'" class="photobank-panel">
          <p class="muted">从这家店已上传的图片银行里选，最多 6 张。不用再传一遍。</p>
          <div class="toolbar" style="margin: 10px 0">
            <el-button :loading="photobankLoading" @click="loadPhotobank">刷新列表</el-button>
            <span class="muted">已选 {{ selectedPhotobank.length }}/6</span>
          </div>
          <div v-if="photobankImages.length" class="photobank-grid">
            <button
              v-for="item in photobankImages"
              :key="item.id"
              type="button"
              class="photobank-item"
              :class="{ 'is-selected': isPhotobankSelected(item) }"
              @click="togglePhotobank(item)"
            >
              <img :src="normalizePhotoUrl(item.url)" :alt="item.file_name" />
              <span>{{ item.file_name || item.id }}</span>
            </button>
          </div>
          <p v-else-if="!photobankLoading" class="muted">还没有拉到图片。先点刷新，或去阿里后台上传后再来。</p>
        </div>
        <el-upload
          v-else-if="photoMode === 'batch'"
          v-model:file-list="batchFiles"
          :auto-upload="false"
          multiple
          accept="image/*"
          drag
          style="width: 100%; margin-top: 8px"
        >
          <div style="padding: 26px 0">把整个文件夹的图拖进来</div>
        </el-upload>
        <div class="step-actions">
          <el-button type="primary" :disabled="!hasPhotos" @click="advancePhoto(1)">下一步，填价格</el-button>
        </div>
      </div>

      <div v-else-if="photoStep === 1" class="step-panel">
        <h3>填价格和起订量</h3>
        <p class="muted">这两项是红线，AI 不会代填。批量时整批共用同一个价和起订量。</p>
        <div class="prop-form" style="margin-top: 8px">
          <div v-if="photoMode === 'single'" class="prop-row">
            <label>货号</label>
            <el-input v-model="form.sku" placeholder="留空则用图片文件名" />
          </div>
          <div class="prop-row">
            <label>单价</label>
            <el-input v-model="form.price" placeholder="12.50">
              <template #append>USD</template>
            </el-input>
          </div>
          <div class="prop-row">
            <label>起订量</label>
            <el-input v-model="form.moq" placeholder="100" />
          </div>
          <div v-if="photoMode === 'single'" class="prop-row">
            <label>补充</label>
            <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选。中文也行，例如：加厚款，可定制 logo" />
          </div>
        </div>
        <div class="step-actions">
          <el-button @click="photoStep = 0">上一步</el-button>
          <el-button type="primary" :disabled="!form.price || !form.moq" @click="advancePhoto(2)">下一步，生成草稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>生成草稿</h3>
        <p class="muted">系统会看图、定类目、对齐属性、写英文标题。大约 20～40 秒一条。</p>
        <div class="step-actions">
          <el-button @click="photoStep = 1">上一步</el-button>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!store.shopId"
            @click="photoMode === 'single' ? submitOne() : submitBatch()"
          >
            {{ photoMode === "single" ? "生成草稿" : "开始批量成稿" }}
          </el-button>
          <span v-if="loading" class="muted">正在成稿，可以先去干别的</span>
        </div>
        <div v-if="batch" style="margin-top: 18px">
          <p>共 {{ batch.count }} 个商品，已完成 {{ progress.done }} 个。关掉页面也不影响。</p>
          <el-progress :percentage="percent" :stroke-width="10" />
          <el-button style="margin-top: 12px" @click="$router.push('/drafts?filter=pending')">去商品里核对</el-button>
        </div>
      </div>
    </template>

    <!-- 没图：平台生成套图 -->
    <template v-else-if="tab === 'ai'">
      <FishboneSteps v-model="aiStep" :steps="aiSteps" :reached="aiReached" />

      <div v-if="aiStep === 0" class="step-panel">
        <h3>写出品名和已知事实</h3>
        <p class="muted">没有实拍时才走这里。平台按国际站画 6 张：白底主图、尺寸、细节、场景、外箱、OEM。生成图不是实拍，草稿会标黄。</p>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="可以猜，但必须有依据"
          description="套图按你写的规格和上传的主图样子来。没写的尺寸、装箱量、色数、认证一律不编。有主图时务必上传，模型按这张货长，不另设计一款。"
          style="margin: 12px 0"
        />
        <el-form label-width="88px" style="max-width: 720px; margin-top: 12px">
          <el-form-item label="类目">
            <div>
              <el-button @click="openAiCategory">{{ aiForm.categoryName || "选择国际站类目" }}</el-button>
              <p class="muted" style="margin: 6px 0 0">从这家店的官方类目树选到可发布的叶子。不选也能先出图。</p>
            </div>
          </el-form-item>
          <el-form-item label="出图风格">
            <div>
              <div class="family-chips">
                <button
                  v-for="item in templates.families || []"
                  :key="item.id"
                  type="button"
                  class="family-chip"
                  :class="{ 'is-active': aiForm.familyId === item.id }"
                  @click="aiForm.familyId = aiForm.familyId === item.id ? '' : item.id"
                >
                  {{ item.name }}
                </button>
              </div>
              <p class="muted" style="margin: 6px 0 0">可不选。不选则按官方类目和品名自动匹配。</p>
            </div>
          </el-form-item>
          <el-form-item label="品名">
            <el-input v-model="aiForm.productName" placeholder="例如 油漆刷 / colored pencil set / taza de cerámica" />
          </el-form-item>
          <el-form-item label="材质">
            <el-input v-model="aiForm.material" placeholder="可选。例如 猪鬃、拉丝铁皮箍、哑光木柄。没写就不指定材质。" />
          </el-form-item>
          <el-form-item label="尺寸">
            <el-input v-model="aiForm.size" placeholder="可选。例如 25cm。没写则尺寸图不加任何数字。" />
          </el-form-item>
          <el-form-item label="装箱量">
            <el-input v-model="aiForm.packCount" placeholder="可选。例如 100 pcs / carton。没写则外箱不加数量。" />
          </el-form-item>
          <el-form-item label="颜色">
            <el-input v-model="aiForm.colors" placeholder="可选。多个用逗号隔开。没写就不编色号。" />
          </el-form-item>
          <el-form-item label="补充">
            <el-input v-model="aiForm.note" type="textarea" :rows="2" placeholder="只写你确定的事实。中文也行。不要写没核实的认证或数字。" />
          </el-form-item>
          <el-form-item label="主图">
            <div>
              <el-upload
                :auto-upload="false"
                :limit="1"
                accept="image/*"
                :on-change="onReferenceFile"
                :on-remove="() => (aiForm.referenceFile = null)"
              >
                <el-button>上传商品主图</el-button>
              </el-upload>
              <el-input
                v-model="aiForm.referenceUrl"
                placeholder="或者贴一张产品图网址"
                style="margin-top: 8px"
              />
              <p class="muted" style="margin: 6px 0 0">有实拍务必给一张。套图按这张货的样子和下面的规格来，不另设计。</p>
            </div>
          </el-form-item>
        </el-form>
        <div class="step-actions">
          <el-button type="primary" :loading="aiForm.planning" @click="startGenerate">生成套图</el-button>
        </div>
      </div>

      <div v-else-if="aiStep === 1" class="step-panel">
        <h3>{{ imageJob?.status === "succeeded" ? "套图已画好" : "正在出图" }}</h3>
        <p class="muted">
          套用「{{ imageJob?.family?.name || "类目模板" }}」。
          <span v-if="imageJob?.product_brief && imageJob.product_brief !== imageJob.product_name">
            出图按「{{ imageJob.product_brief }}」。
          </span>
          {{ imageJob?.progress || "排队出图" }}
          这 6 张是平台生成图，不是实拍。
        </p>
        <el-progress :percentage="imagePercent" :stroke-width="10" style="margin: 14px 0" />
        <div class="slot-grid">
          <div v-for="slot in imageJob?.slots || []" :key="slot.id" class="slot-card">
            <div class="slot-photo">
              <img v-if="slot.url" :src="slot.url" :alt="slot.name" />
              <span v-else class="muted">{{ slot.status === "running" ? "正在画" : "排队" }}</span>
            </div>
            <div class="slot-head">
              <b>{{ slot.index }}. {{ slot.name }}</b>
            </div>
            <p class="muted">买手看这张：{{ slot.buyer_job }}</p>
          </div>
        </div>
        <el-alert
          v-if="imageJob?.status === 'failed'"
          type="error"
          :title="imageJob.error || '出图失败，请再试一次'"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <div class="step-actions">
          <el-button @click="aiStep = 0">上一步</el-button>
          <el-button v-if="imageJob?.status === 'failed'" @click="startGenerate">再画一次</el-button>
          <el-button type="primary" :disabled="imageJob?.status !== 'succeeded'" @click="advanceAi(2)">
            下一步，填价格
          </el-button>
        </div>
      </div>

      <div v-else-if="aiStep === 2" class="step-panel">
        <h3>填价格和起订量</h3>
        <p class="muted">这两项是红线，AI 不会代填。</p>
        <div class="prop-form" style="margin-top: 8px">
          <div class="prop-row">
            <label>货号</label>
            <el-input v-model="form.sku" placeholder="留空则用品名" />
          </div>
          <div class="prop-row">
            <label>单价</label>
            <el-input v-model="form.price" placeholder="12.50">
              <template #append>USD</template>
            </el-input>
          </div>
          <div class="prop-row">
            <label>起订量</label>
            <el-input v-model="form.moq" placeholder="100" />
          </div>
          <div class="prop-row">
            <label>补充</label>
            <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选。中文也行" />
          </div>
        </div>
        <div class="step-actions">
          <el-button @click="aiStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!form.price || !form.moq" @click="advanceAi(3)">下一步，生成草稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>生成草稿</h3>
        <p class="muted">用刚画好的 6 张图成稿。大约 20～40 秒。草稿里会标黄：这不是实拍。</p>
        <div class="step-actions">
          <el-button @click="aiStep = 2">上一步</el-button>
          <el-button type="primary" :loading="loading" :disabled="!store.shopId || imageJob?.status !== 'succeeded'" @click="submitGenerated">
            生成草稿
          </el-button>
        </div>
      </div>
    </template>

    <!-- 批量上品：选类目 → 导入资料 → 核对编辑 → 成稿 -->
    <template v-else-if="tab === 'doc'">
      <FishboneSteps v-model="docStep" :steps="docSteps" :reached="docReached" />

      <div v-if="docStep === 0" class="step-panel">
        <h3>这批货是哪一类</h3>
        <p class="muted">批量上品整批共用一个叶子类目。有实拍、平台画图不用先选类目。</p>
        <div style="margin-top: 16px">
          <el-button @click="openDocCategory">{{ doc.categoryName || sheetPlan.category_name || "选择类目" }}</el-button>
          <p v-if="officialLoading" class="muted" style="margin-top: 6px">正在拉类目属性…</p>
          <p v-else-if="schemaColumnLabels.length" class="muted" style="margin-top: 10px">
            表里会带上必填属性：{{ schemaColumnLabels.join("、") }}
          </p>
        </div>
        <div v-if="doc.categoryId" class="category-next-box">
          <b>选完类目后，批量上品可以走：</b>
          <ul>
            <li><b>上传资料</b> — 报价单、目录、已有 xlsx/csv（表格直接识别；照片/PDF 由 AI 提取）</li>
            <li><b>下载短表</b> — 离线填货号、价、起订量、必填属性，填好再上传解析</li>
            <li><b>没图的行</b> — 后面可选按品名画套图，或跳过</li>
          </ul>
          <p class="muted">标题、关键词、选填属性 AI 补；信息质量分 5.0 且审过才能发。</p>
        </div>
        <div class="step-actions">
          <el-button type="primary" :disabled="!doc.categoryId" @click="advanceDoc(1)">下一步，导入资料</el-button>
        </div>
      </div>

      <div v-else-if="docStep === 1" class="step-panel">
        <h3>导入资料</h3>
        <p class="muted">支持 xlsx、csv、图片、txt、pdf，可多文件。领星 / 店小秘 / 马帮表头也能识别。</p>
        <div class="toolbar" style="margin: 12px 0">
          <el-button :disabled="!doc.categoryId" @click="downloadDocTemplate">下载空白短表</el-button>
          <span class="muted">离线填好再拖回来，和上传报价单走同一条路</span>
        </div>
        <el-upload
          v-model:file-list="docFiles"
          :auto-upload="false"
          multiple
          accept=".xlsx,.xls,.xlsm,.csv,.txt,.md,.jpg,.jpeg,.png,.webp,.pdf"
          drag
          style="margin-top: 14px"
        >
          <div style="padding: 22px 0">把工厂报价单、目录、表格拖到这里（可多文件）</div>
        </el-upload>
        <div class="step-actions" style="margin-top: 16px">
          <el-button @click="docStep = 0">上一步</el-button>
          <el-button type="primary" :loading="docGrid.loading" :disabled="!docFiles.length" @click="parseDocuments">
            AI 解析并填表
          </el-button>
        </div>
      </div>

      <div v-else-if="docStep === 2" class="step-panel">
        <h3>核对商品表（可直接改）</h3>
        <p class="muted">
          共 {{ docGrid.row_count || docGrid.rows.length }} 个商品，价量齐 {{ docGrid.ready_count || 0 }} 个。
          <span v-if="docGrid.source">来源：{{ docGrid.source }}</span>
        </p>
        <el-alert
          v-for="warning in docGrid.warnings || []"
          :key="warning"
          type="warning"
          :title="warning"
          :closable="false"
          style="margin: 10px 0"
        />
        <div class="doc-grid-toolbar">
          <el-button size="small" @click="addDocRow">加一行</el-button>
          <el-button size="small" :loading="docGrid.checking" @click="recheckDocGrid">重新校验</el-button>
        </div>
        <div class="doc-grid-wrap">
          <table class="doc-grid">
            <thead>
              <tr>
                <th>#</th>
                <th v-for="col in docGrid.columns" :key="col.id">
                  {{ col.label }}<span v-if="col.required" class="need">必填</span>
                </th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in docGrid.rows" :key="row.line || index">
                <td>{{ index + 1 }}</td>
                <td v-for="col in docGrid.columns" :key="`${index}-${col.id}`">
                  <el-select
                    v-if="col.options?.length"
                    v-model="row[col.id]"
                    filterable
                    clearable
                    placeholder="选"
                    size="small"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="opt in col.options"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.label"
                    />
                  </el-select>
                  <el-input v-else v-model="row[col.id]" size="small" />
                </td>
                <td><el-button text type="danger" @click="removeDocRow(index)">删</el-button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="docGrid.row_issues?.length" class="row-issues">
          <b>成稿前先看这几行</b>
          <ul>
            <li v-for="(issue, index) in docGrid.row_issues.slice(0, 16)" :key="index">
              <span :class="['dot', issue.level]"></span>
              第 {{ issue.line }} 行 {{ issue.sku }}：{{ issue.message }}
            </li>
          </ul>
        </div>
        <div class="step-actions">
          <el-button @click="docStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!docGrid.rows.length" @click="advanceDoc(3)">下一步，图怎么处理</el-button>
        </div>
      </div>

      <div v-else-if="docStep === 3" class="step-panel">
        <h3>这批图怎么处理</h3>
        <p class="muted">一张表里可以有的行有图、有的没图，图多图少都按下面两句话走，不按张数分路。</p>
        <div class="policy-block">
          <small>有图的行</small>
          <div class="path-grid">
            <button type="button" class="path-card" :class="{ 'is-active': excel.photoPolicy === 'keep' }" @click="excel.photoPolicy = 'keep'">
              <small>工厂图已经能用</small>
              <b>原图上架</b>
              <p class="muted">有几张用几张，不改、不补。</p>
            </button>
            <button type="button" class="path-card" :class="{ 'is-active': excel.photoPolicy === 'complete' }" @click="excel.photoPolicy = 'complete'">
              <small>推荐</small>
              <b>原图留下，再补转化位</b>
              <p class="muted">实拍不动，缺的转化位平台补并标黄。</p>
            </button>
            <button type="button" class="path-card" :class="{ 'is-active': excel.photoPolicy === 'boost' }" @click="excel.photoPolicy = 'boost'">
              <small>图太乱</small>
              <b>当参考，重画套图</b>
              <p class="muted">6 张重画并标黄。</p>
            </button>
          </div>
        </div>
        <div class="policy-block">
          <small>没图的行</small>
          <div class="path-grid path-grid-2">
            <button type="button" class="path-card" :class="{ 'is-active': excel.emptyPolicy === 'draw' }" @click="excel.emptyPolicy = 'draw'">
              <b>按品名画套图</b>
            </button>
            <button type="button" class="path-card" :class="{ 'is-active': excel.emptyPolicy === 'skip' }" @click="excel.emptyPolicy = 'skip'">
              <b>跳过没图的行</b>
            </button>
          </div>
        </div>
        <p class="muted" style="margin-top: 16px">{{ excelImageUploadHint }}</p>
        <el-upload
          v-model:file-list="excelImages"
          :auto-upload="false"
          multiple
          accept="image/*"
          drag
          style="margin-top: 10px"
        >
          <div style="padding: 22px 0">有本地图就拖进来，按货号命名</div>
        </el-upload>
        <div class="step-actions">
          <el-button @click="docStep = 2">上一步</el-button>
          <el-button type="primary" @click="advanceDoc(4)">下一步，开始成稿</el-button>
        </div>
      </div>

      <div v-else-if="docStep === 4" class="step-panel">
        <h3>批量成稿</h3>
        <p class="muted">{{ excelGoHint }} 导入后逐条核对，信息质量分 5.0 且审过才能发。</p>
        <div class="step-actions">
          <el-button @click="docStep = 3">上一步</el-button>
          <el-button
            type="primary"
            :loading="docGrid.loading"
            :disabled="!docGrid.rows.length || !store.shopId || !doc.categoryId"
            @click="importDocRows"
          >
            批量成稿（{{ docGrid.rows.length }} 个）
          </el-button>
        </div>
        <div v-if="doc.batch" style="margin-top: 18px">
          <p>
            共 {{ doc.batch.count }} 个商品，已成稿 {{ docProgress.done }}/{{ doc.batch.count }}。
            <template v-if="docProgress.complete">
              待审 {{ docProgress.pending || 0 }} · 待改 {{ docProgress.counts?.red || 0 }} · 已审可发 {{ docProgress.ready || 0 }}。
            </template>
          </p>
          <el-progress :percentage="docPercent" :stroke-width="10" />
          <div style="margin-top: 12px">
            <el-button type="primary" :disabled="!docProgress.complete" @click="goDocBatchDrafts('pending')">去审这一批</el-button>
          </div>
        </div>
      </div>
    </template>
    </template>

    <CategoryPicker v-model="categoryBrowser" @pick="pickCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import FishboneSteps from "../components/FishboneSteps.vue";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const route = useRoute();
const sessionId = ref("");
const openSessions = ref([]);
const currentTitle = ref("");
const restoring = ref(false);
const tab = ref("single");
const photoMode = ref("single");
const photoSource = ref("upload");
const photobankImages = ref([]);
const selectedPhotobank = ref([]);
const photobankLoading = ref(false);
const photoStep = ref(0);
const photoReached = ref(0);
const aiStep = ref(0);
const aiReached = ref(0);
const docStep = ref(0);
const docReached = ref(0);

const photoSteps = [
  { key: "photos", label: "上传图片" },
  { key: "price", label: "填价格" },
  { key: "draft", label: "生成草稿" },
];
const aiSteps = [
  { key: "name", label: "写出品名" },
  { key: "draw", label: "生成套图" },
  { key: "price", label: "填价格" },
  { key: "draft", label: "生成草稿" },
];
const docSteps = [
  { key: "cat", label: "选类目" },
  { key: "up", label: "导入资料" },
  { key: "edit", label: "核对编辑" },
  { key: "img", label: "图怎么处理" },
  { key: "go", label: "批量成稿" },
];
const templates = ref({ families: [], sources: [] });
const imageJob = ref(null);
const aiForm = reactive({
  familyId: "",
  productName: "",
  material: "",
  size: "",
  packCount: "",
  colors: "",
  note: "",
  referenceUrl: "",
  referenceFile: null,
  planning: false,
  categoryId: "",
  categoryName: "",
});
const categoryTarget = ref("doc");
const loading = ref(false);
const files = ref([]);
const batchFiles = ref([]);
const batch = ref(null);
const progress = ref({ done: 0 });
const form = reactive({ sku: "", price: "", moq: "", note: "" });
const excelImages = ref([]);
const docFiles = ref([]);
const doc = reactive({
  categoryId: "",
  categoryName: "",
  batch: null,
});
const docGrid = reactive({
  columns: [],
  rows: [],
  row_issues: [],
  warnings: [],
  row_count: 0,
  ready_count: 0,
  source: "",
  loading: false,
  checking: false,
});
const docProgress = ref({ done: 0 });
let docTimer = null;
const excel = reactive({
  photoPolicy: "complete",
  emptyPolicy: "draw",
});
const sheetPlan = ref({ user_fills: [], shop_fills: [], ai_fills: [], redline: [], guarantee: "", ai_attrs: [], category_name: "", preview: null, sheet: null });
const officialLoading = ref(false);
const categoryBrowser = ref(false);
let timer = null;
let docTimer = null;
let imageTimer = null;

const coreFillIds = new Set(["sku", "price", "moq", "images", "brand", "name", "note"]);
const schemaColumnLabels = computed(() =>
  (sheetPlan.value.preview?.columns || [])
    .filter((col) => !coreFillIds.has(col.id))
    .map((col) => col.label)
    .filter(Boolean),
);
const excelImageMode = computed(() => `${excel.photoPolicy || "complete"}_${excel.emptyPolicy || "draw"}`);
const excelImageUploadHint = computed(() => {
  if (excel.photoPolicy === "boost") {
    return "有本地图或表里的链接都只当认货参考。没图的行看下面第二条。";
  }
  if (excel.emptyPolicy === "skip") {
    return "有本地图就拖进来，按货号命名。对不上的行会跳过。";
  }
  return "有本地图就拖进来，按货号命名。表里写了链接也不用再传。没对上的行按品名画套图。";
});
const excelGoHint = computed(() => {
  const photoText = {
    keep: "有图的原图上架",
    complete: "有图的原图留下并补转化位",
    boost: "有图的当参考重画套图",
  }[excel.photoPolicy] || "有图的按你选的规则处理";
  const emptyText = excel.emptyPolicy === "skip" ? "没图的跳过" : "没图的按品名画套图并标黄";
  return `${photoText}，${emptyText}。后台一条一条过。`;
});
const docPercent = computed(() => {
  if (!doc.batch?.count) return 0;
  return Math.min(100, Math.round((docProgress.value.done / doc.batch.count) * 100));
});
const percent = computed(() => {
  if (!batch.value?.count) return 0;
  return Math.min(100, Math.round((progress.value.done / batch.value.count) * 100));
});
const hasPhotos = computed(() => {
  if (photoMode.value === "batch") return batchFiles.value.length;
  if (photoSource.value === "photobank") return selectedPhotobank.value.length;
  return files.value.length;
});
const imagePercent = computed(() => {
  const total = imageJob.value?.total || 6;
  return Math.min(100, Math.round(((imageJob.value?.done || 0) / total) * 100));
});

function applyExcelImageMode(raw, photo, empty) {
  if (photo && empty) {
    excel.photoPolicy = photo;
    excel.emptyPolicy = empty;
    return;
  }
  const aliases = {
    mixed: "keep_draw",
    photos_only: "keep_skip",
    generate_all: "boost_draw",
    keep: "keep_draw",
    complete: "complete_draw",
    boost: "boost_draw",
  };
  const mode = aliases[raw] || raw || "complete_draw";
  const [nextPhoto, nextEmpty] = String(mode).split("_");
  excel.photoPolicy = ["keep", "complete", "boost"].includes(nextPhoto) ? nextPhoto : "complete";
  excel.emptyPolicy = nextEmpty === "skip" ? "skip" : "draw";
}

function pathToTab(path) {
  if (path === "ai") return "ai";
  if (path === "doc" || path === "excel" || path === "full") return "doc";
  return "single";
}

function migrateLegacyExcelSession(session, payload) {
  if (session.path !== "excel" && session.path !== "full") return;
  const ep = payload.excel || {};
  if (!doc.categoryId && ep.categoryId) {
    doc.categoryId = ep.categoryId;
    doc.categoryName = ep.categoryName || payload.categoryName || "";
  }
  if (!doc.batch && ep.batch) doc.batch = ep.batch;
  applyExcelImageMode(ep.imageMode, ep.photoPolicy, ep.emptyPolicy);
  const stepMap = { 0: 0, 1: 1, 2: 1, 3: 3, 4: 4 };
  docStep.value = stepMap[session.step ?? 0] ?? 0;
  docReached.value = Math.max(session.reached ?? 0, docStep.value);
}

function sessionPayload() {
  return {
    photoMode: photoMode.value,
    form: { ...form },
    aiForm: {
      familyId: aiForm.familyId,
      productName: aiForm.productName,
      material: aiForm.material,
      size: aiForm.size,
      packCount: aiForm.packCount,
      colors: aiForm.colors,
      note: aiForm.note,
      referenceUrl: aiForm.referenceUrl,
      categoryId: aiForm.categoryId,
      categoryName: aiForm.categoryName,
    },
    excel: {
      categoryId: doc.categoryId,
      categoryName: doc.categoryName,
      batch: doc.batch,
      imageMode: excelImageMode.value,
      photoPolicy: excel.photoPolicy,
      emptyPolicy: excel.emptyPolicy,
    },
    doc: {
      categoryId: doc.categoryId,
      categoryName: doc.categoryName,
      columns: docGrid.columns,
      rows: docGrid.rows,
      row_issues: docGrid.row_issues,
      warnings: docGrid.warnings,
      row_count: docGrid.row_count,
      ready_count: docGrid.ready_count,
      source: docGrid.source,
      batch: doc.batch,
      imageMode: excelImageMode.value,
      photoPolicy: excel.photoPolicy,
      emptyPolicy: excel.emptyPolicy,
    },
    categoryName: sheetPlan.value.category_name || doc.categoryName || "",
    rowCount:
      docGrid.row_count ||
      docGrid.rows.length ||
      doc.batch?.count ||
      batch.value?.count ||
      0,
    imageJobId: imageJob.value?.id || "",
    batchId: batch.value?.batch_id || doc.batch?.batch_id || "",
  };
}

function currentStep() {
  if (tab.value === "ai") return aiStep.value;
  if (tab.value === "doc") return docStep.value;
  return photoStep.value;
}

function currentReached() {
  if (tab.value === "ai") return aiReached.value;
  if (tab.value === "doc") return docReached.value;
  return photoReached.value;
}

async function loadOpenSessions() {
  if (!store.user) return;
  try {
    const data = await api.feedSessions(store.shopId);
    openSessions.value = data.sessions || [];
  } catch {
    openSessions.value = [];
  }
}

async function persistSession() {
  if (!sessionId.value || restoring.value) return;
  try {
    const saved = await api.saveFeedSession(sessionId.value, {
      shop_id: store.shopId || "",
      step: currentStep(),
      reached: currentReached(),
      payload: sessionPayload(),
    });
    currentTitle.value = saved.title || currentTitle.value;
  } catch {
    /* keep typing even if save is slow */
  }
}

async function syncKind(kind, list) {
  if (!sessionId.value || restoring.value || !store.user) return;
  const raws = (list || []).filter((item) => item.raw);
  const keep = (list || []).filter((item) => !item.raw && item.name).map((item) => item.name);
  try {
    if (!raws.length && !list?.length) {
      const body = new FormData();
      body.append("kind", kind);
      body.append("keep", "");
      await api.uploadFeedSessionFiles(sessionId.value, body);
      return;
    }
    if (!raws.length) return;
    const body = new FormData();
    body.append("kind", kind);
    body.append("keep", keep.join(","));
    raws.forEach((item) => body.append("files", item.raw));
    await api.uploadFeedSessionFiles(sessionId.value, body);
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("不在了") || msg.includes("登录")) {
      if (sessionId.value) {
        sessionId.value = "";
        router.replace({ query: {} });
        await loadOpenSessions();
      }
    }
  }
}

function filesFromSession(session, kind) {
  return (session.files || [])
    .filter((item) => item.kind === kind)
    .map((item) => ({ name: item.name, url: item.url, status: "success" }));
}

function applySession(session) {
  restoring.value = true;
  sessionId.value = session.id;
  currentTitle.value = session.title || session.path_label;
  tab.value = pathToTab(session.path);
  const payload = session.payload || {};
  photoMode.value = payload.photoMode || "single";
  Object.assign(form, { sku: "", price: "", moq: "", note: "", ...(payload.form || {}) });
  Object.assign(aiForm, {
    familyId: "",
    productName: "",
    material: "",
    size: "",
    packCount: "",
    colors: "",
    note: "",
    referenceUrl: "",
    categoryId: "",
    categoryName: "",
    ...(payload.aiForm || {}),
    referenceFile: null,
    planning: false,
  });
  if (payload.excel) {
    applyExcelImageMode(payload.excel.imageMode, payload.excel.photoPolicy, payload.excel.emptyPolicy);
  }
  if (payload.doc) {
    doc.categoryId = payload.doc.categoryId || "";
    doc.categoryName = payload.doc.categoryName || payload.categoryName || "";
    doc.batch = payload.doc.batch || null;
    docGrid.columns = payload.doc.columns || [];
    docGrid.rows = payload.doc.rows || [];
    docGrid.row_issues = payload.doc.row_issues || [];
    docGrid.warnings = payload.doc.warnings || [];
    docGrid.row_count = payload.doc.row_count || docGrid.rows.length;
    docGrid.ready_count = payload.doc.ready_count || 0;
    docGrid.source = payload.doc.source || "";
    applyExcelImageMode(payload.doc.imageMode, payload.doc.photoPolicy, payload.doc.emptyPolicy);
  }
  files.value = filesFromSession(session, "photos");
  batchFiles.value = filesFromSession(session, "batch");
  excelImages.value = filesFromSession(session, "excel_images");
  docFiles.value = filesFromSession(session, "doc");
  imageJob.value = payload.imageJobId ? { id: payload.imageJobId, status: "queued", slots: [] } : null;
  batch.value = payload.batchId && tab.value === "single" ? { batch_id: payload.batchId, count: payload.rowCount || 0 } : null;
  if (tab.value === "ai") {
    aiStep.value = session.step || 0;
    aiReached.value = session.reached || 0;
  } else if (tab.value === "doc") {
    if (session.path === "excel" || session.path === "full") {
      migrateLegacyExcelSession(session, payload);
    } else {
      docStep.value = session.step || 0;
      docReached.value = session.reached || 0;
    }
  } else {
    photoStep.value = session.step || 0;
    photoReached.value = session.reached || 0;
  }
  restoring.value = false;
}

async function startPath(path) {
  try {
    const sessionPath = path === "excel" || path === "full" ? "doc" : path;
    const created = await api.createFeedSession({ path: sessionPath, shop_id: store.shopId || "" });
    if (sessionPath === "doc") {
      docStep.value = 0;
      docReached.value = 0;
      doc.categoryId = "";
      doc.categoryName = "";
      doc.batch = null;
      docGrid.columns = [];
      docGrid.rows = [];
      docGrid.row_issues = [];
      docGrid.warnings = [];
      docGrid.row_count = 0;
      docGrid.ready_count = 0;
      docGrid.source = "";
      docFiles.value = [];
    }
    applySession(created);
    router.replace({ query: { session: created.id } });
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function resumeSession(id) {
  try {
    const session = await api.feedSession(id);
    applySession(session);
    router.replace({ query: { session: id } });
    if (imageJob.value?.id) {
      clearInterval(imageTimer);
      imageTimer = setInterval(pollImageJob, 2000);
      await pollImageJob();
    }
    if (batch.value?.batch_id) {
      clearInterval(timer);
      timer = setInterval(poll, 3000);
      await poll();
    }
    if (doc.batch?.batch_id) {
      clearInterval(docTimer);
      docTimer = setInterval(pollDoc, 3000);
      await pollDoc();
    }
    if (doc.categoryId) {
      await loadSheetPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
      loadOfficialAttrs();
    }
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("不在了")) {
      ElMessage.warning("这条做到一半的记录已失效，请重新选路");
      sessionId.value = "";
      router.replace({ query: {} });
      await loadOpenSessions();
      return;
    }
    ElMessage.error(error.message);
  }
}

async function dropSession(id) {
  try {
    await api.dropFeedSession(id);
    if (sessionId.value === id) {
      sessionId.value = "";
      router.replace({ query: {} });
    }
    await loadOpenSessions();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function dropCurrent() {
  if (sessionId.value) await dropSession(sessionId.value);
}

async function backToChooser() {
  await persistSession();
  sessionId.value = "";
  router.replace({ query: {} });
  await loadOpenSessions();
}

function advancePhoto(index) {
  photoReached.value = Math.max(photoReached.value, index);
  photoStep.value = index;
  persistSession();
}

function advanceAi(index) {
  aiReached.value = Math.max(aiReached.value, index);
  aiStep.value = index;
  persistSession();
}

onMounted(async () => {
  try {
    templates.value = await api.imageTemplates();
  } catch (error) {
    ElMessage.error(error.message);
  }
  await loadOpenSessions();
  if (route.query.session) {
    await resumeSession(String(route.query.session));
  }
});

let saveTimer = null;
watch([() => form.sku, () => form.price, () => form.moq, () => form.note], () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(persistSession, 500);
});
watch(
  () => [
    aiForm.productName,
    aiForm.material,
    aiForm.size,
    aiForm.packCount,
    aiForm.colors,
    aiForm.note,
    aiForm.referenceUrl,
    aiForm.categoryId,
    aiForm.familyId,
  ],
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 500);
  },
);
watch(files, () => syncKind("photos", files.value), { deep: true });
watch(batchFiles, () => syncKind("batch", batchFiles.value), { deep: true });
watch(excelImages, () => syncKind("excel_images", excelImages.value), { deep: true });
watch(
  () => [excel.photoPolicy, excel.emptyPolicy],
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 400);
  },
);
watch(
  () => [docStep.value, doc.categoryId, doc.categoryName, docGrid.rows],
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 500);
  },
  { deep: true },
);
watch(docFiles, () => syncKind("doc", docFiles.value), { deep: true });

function onReferenceFile(file) {
  aiForm.referenceFile = file?.raw || null;
}

async function startGenerate() {
  if (!aiForm.productName && !aiForm.note && !aiForm.familyId) {
    ElMessage.warning("先写品名，或选一个类目");
    return;
  }
  aiForm.planning = true;
  try {
    const refs = [];
    if (aiForm.referenceFile) {
      const body = new FormData();
      body.append("file", aiForm.referenceFile);
      const stored = await api.uploadReference(body);
      if (stored?.url) refs.push(stored.url);
    }
    if (aiForm.referenceUrl.trim()) refs.push(aiForm.referenceUrl.trim());
    imageJob.value = await api.generateImages({
      family_id: aiForm.familyId,
      product_name: aiForm.productName,
      material: aiForm.material,
      note: aiForm.note,
      colors: aiForm.colors.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      specs: {
        size: aiForm.size.trim(),
        pack_count: aiForm.packCount.trim(),
      },
      category_id: aiForm.categoryId,
      category_hint: aiForm.categoryName,
      reference_urls: refs,
    });
    if (imageJob.value?.family?.id) aiForm.familyId = imageJob.value.family.id;
    await persistSession();
    advanceAi(1);
    clearInterval(imageTimer);
    imageTimer = setInterval(pollImageJob, 2000);
    await pollImageJob();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    aiForm.planning = false;
  }
}

async function pollImageJob() {
  if (!imageJob.value?.id) return;
  try {
    imageJob.value = await api.imageJob(imageJob.value.id);
    if (imageJob.value.status === "succeeded") {
      clearInterval(imageTimer);
      aiReached.value = Math.max(aiReached.value, 2);
      ElMessage.success("6 张套图已画好");
    } else if (imageJob.value.status === "failed") {
      clearInterval(imageTimer);
      ElMessage.error(imageJob.value.error || "出图失败，请再试一次");
    }
  } catch (error) {
    clearInterval(imageTimer);
    ElMessage.error(error.message);
  }
}

async function submitGenerated() {
  if (!imageJob.value?.id) {
    ElMessage.warning("先生成套图");
    return;
  }
  loading.value = true;
  try {
    const draft = await api.feedFromGenerated({
      shop_id: store.shopId,
      job_id: imageJob.value.id,
      sku: form.sku,
      price: form.price,
      moq: form.moq,
      note: form.note,
      category_id: aiForm.categoryId || imageJob.value.category_id || "",
      session_id: sessionId.value,
    });
    ElMessage.success(`草稿已生成：${draft.category_name || "待定类目"}`);
    sessionId.value = "";
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function loadSheetPlan(override = null) {
  const categoryId = override?.categoryId ?? doc.categoryId ?? "";
  const categoryName = override?.categoryName ?? doc.categoryName ?? "";
  try {
    sheetPlan.value = await api.excelSheetPlan({
      shop_id: store.shopId || "",
      category_id: categoryId,
      category_name: categoryName,
      style: "simple",
    });
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("店铺不存在")) {
      await store.ensureShops();
      if (store.shopId) {
        sheetPlan.value = await api.excelSheetPlan({
          shop_id: store.shopId,
          category_id: categoryId,
          category_name: categoryName,
          style: "simple",
        });
        return;
      }
    }
    throw error;
  }
}

function syncDocColumnsFromPlan() {
  const preview = sheetPlan.value.preview?.columns || [];
  if (!preview.length) return;
  docGrid.columns = preview.map((col) => ({
    id: col.id,
    label: col.label,
    required: col.required,
    options: col.options,
    kind: col.options?.length ? "select" : "text",
  }));
}

async function loadOfficialAttrs() {
  if (!store.shopId || !doc.categoryId) return;
  officialLoading.value = true;
  try {
    const data = await api.officialExcelAttrs(store.shopId, doc.categoryId);
    sheetPlan.value = {
      ...sheetPlan.value,
      ai_attrs: data.ai_attrs || [],
      ai_fills: data.ai_fills || sheetPlan.value.ai_fills,
    };
    syncDocColumnsFromPlan();
  } catch {
    /* cached sheet-plan already has whatever we have locally */
    syncDocColumnsFromPlan();
  } finally {
    officialLoading.value = false;
  }
}

function openDocCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryTarget.value = "doc";
  categoryBrowser.value = true;
}

function advanceDoc(index) {
  docReached.value = Math.max(docReached.value, index);
  docStep.value = index;
  persistSession();
}

async function parseDocuments() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  if (!docFiles.value.some((item) => item.raw)) {
    ElMessage.warning("先上传资料");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", doc.categoryId);
  body.append("category_name", doc.categoryName || sheetPlan.value.category_name || "");
  body.append("image_mode", excelImageMode.value);
  docFiles.value.forEach((item) => item.raw && body.append("files", item.raw));
  docGrid.loading = true;
  try {
    const result = await api.excelDocParse(body);
    docGrid.columns = result.columns || [];
    docGrid.rows = result.rows || [];
    docGrid.row_issues = result.row_issues || [];
    docGrid.warnings = result.warnings || [];
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.source = result.source || "";
    await persistSession();
    advanceDoc(2);
    ElMessage.success(`识别到 ${docGrid.row_count} 个商品，可直接在表里改`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
  }
}

async function recheckDocGrid() {
  if (!docGrid.rows.length) return;
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", doc.categoryId);
  body.append("image_mode", excelImageMode.value);
  body.append("rows", JSON.stringify(docGrid.rows));
  docGrid.checking = true;
  try {
    const result = await api.excelGridCheck(body);
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.row_issues = result.row_issues || [];
    await persistSession();
    ElMessage.success(`校验完成：${docGrid.ready_count}/${docGrid.row_count} 个价量齐`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.checking = false;
  }
}

function addDocRow() {
  const row = { line: docGrid.rows.length + 2 };
  (docGrid.columns.length ? docGrid.columns : sheetPlan.value.preview?.columns || []).forEach((col) => {
    row[col.id] = "";
  });
  docGrid.rows.push(row);
  docGrid.row_count = docGrid.rows.length;
  persistSession();
}

function removeDocRow(index) {
  docGrid.rows.splice(index, 1);
  docGrid.row_count = docGrid.rows.length;
  persistSession();
}

async function importDocRows() {
  if (!docGrid.rows.length) {
    ElMessage.warning("表里还没有商品");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("category_id", doc.categoryId);
  body.append("session_id", sessionId.value);
  body.append("image_mode", excelImageMode.value);
  body.append("rows", JSON.stringify(docGrid.rows));
  excelImages.value.forEach((item) => item.raw && body.append("images", item.raw));
  docGrid.loading = true;
  try {
    doc.batch = await api.excelImportRows(body);
    docProgress.value = { done: 0 };
    sessionId.value = "";
    clearInterval(docTimer);
    docTimer = setInterval(pollDoc, 3000);
    ElMessage.success(`已接收 ${doc.batch.count} 个商品，后台在成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
  }
}

async function pollDoc() {
  if (!doc.batch) return;
  try {
    docProgress.value = await api.batchProgress(doc.batch.batch_id, { total: doc.batch.count });
    if (docProgress.value.complete) clearInterval(docTimer);
  } catch {
    clearInterval(docTimer);
  }
}

function goDocBatchDrafts(filter = "pending") {
  router.push({ path: "/drafts", query: { batch_id: doc.batch.batch_id, filter } });
}

function downloadDocTemplate() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  window.location.href = api.excelTemplateUrl("simple", "", {
    categoryId: doc.categoryId,
    shopId: store.shopId,
    categoryName: doc.categoryName || sheetPlan.value.category_name,
  });
}

function openAiCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryTarget.value = "ai";
  categoryBrowser.value = true;
}

async function pickCategory(node) {
  if (categoryTarget.value === "doc") {
    doc.categoryId = node.category_id;
    doc.categoryName = node.path_label || node.label || node.name || node.cn_name || "";
    try {
      await loadSheetPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
      syncDocColumnsFromPlan();
      ElMessage.success(`已选「${sheetPlan.value.category_name || doc.categoryName}」，上传资料后 AI 会按这些列填表`);
      loadOfficialAttrs();
    } catch (error) {
      ElMessage.error(error.message);
    }
    return;
  }
  if (categoryTarget.value === "ai") {
    aiForm.categoryId = node.category_id;
    aiForm.categoryName = node.path_label || node.label || node.name || node.cn_name || "";
    ElMessage.success(`已选「${aiForm.categoryName}」`);
    api
      .planImages({
        product_name: aiForm.productName,
        category_hint: aiForm.categoryName,
        note: aiForm.note,
      })
      .then((planned) => {
        aiForm.familyId = planned.family?.id || "";
      })
      .catch(() => {});
  }
}

onUnmounted(() => {
  clearInterval(timer);
  clearInterval(docTimer);
  clearInterval(imageTimer);
});

async function loadPhotobank() {
  if (!store.shopId) return;
  photobankLoading.value = true;
  try {
    const data = await api.photobank(store.shopId, { page: 1, page_size: 60 });
    photobankImages.value = data.images || [];
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    photobankLoading.value = false;
  }
}

function normalizePhotoUrl(url) {
  if (!url) return "";
  return url.startsWith("//") ? `https:${url}` : url;
}

function isPhotobankSelected(item) {
  return selectedPhotobank.value.some((row) => row.id === item.id);
}

function togglePhotobank(item) {
  const index = selectedPhotobank.value.findIndex((row) => row.id === item.id);
  if (index >= 0) {
    selectedPhotobank.value.splice(index, 1);
    return;
  }
  if (selectedPhotobank.value.length >= 6) {
    ElMessage.warning("最多选 6 张");
    return;
  }
  selectedPhotobank.value.push(item);
}

watch(
  () => [photoSource.value, store.shopId],
  () => {
    if (photoSource.value === "photobank" && store.shopId && !photobankImages.value.length) {
      loadPhotobank();
    }
  },
);

async function submitOne() {
  if (photoSource.value === "photobank") {
    if (!selectedPhotobank.value.length) {
      ElMessage.warning("至少选一张图片银行的图");
      return;
    }
  } else if (!files.value.length) {
    ElMessage.warning("至少传一张图");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("sku", form.sku);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("note", form.note);
  body.append("session_id", sessionId.value);
  if (photoSource.value === "photobank") {
    body.append(
      "photobank_images",
      JSON.stringify(
        selectedPhotobank.value.map((item) => ({
          id: item.id,
          file_id: item.file_id || item.id,
          file_name: item.file_name,
          url: item.url,
        })),
      ),
    );
  } else {
    files.value.forEach((item) => item.raw && body.append("files", item.raw));
  }
  loading.value = true;
  try {
    const draft = await api.feed(body);
    ElMessage.success(`草稿已生成：${draft.category_name || "待定类目"}`);
    sessionId.value = "";
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function submitBatch() {
  if (!batchFiles.value.length) {
    ElMessage.warning("先把图片拖进来");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("session_id", sessionId.value);
  batchFiles.value.forEach((item) => item.raw && body.append("files", item.raw));
  loading.value = true;
  try {
    batch.value = await api.feedBatch(body);
    progress.value = { done: 0 };
    sessionId.value = "";
    clearInterval(timer);
    timer = setInterval(poll, 3000);
    ElMessage.success(`已拆成 ${batch.value.count} 个商品，正在后台成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function poll() {
  if (!batch.value) return;
  try {
    progress.value = await api.batchProgress(batch.value.batch_id);
    if (progress.value.done >= batch.value.count) clearInterval(timer);
  } catch {
    clearInterval(timer);
  }
}
</script>

<style scoped>
.path-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 18px;
}
.path-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.path-grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (min-width: 960px) {
  .path-grid-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (min-width: 960px) {
  .path-grid-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
.schema-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 8px;
}
.schema-stat {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  font-size: 13px;
}
.schema-stat.is-required {
  background: #fee2e2;
  color: #991b1b;
}
.schema-block summary {
  cursor: pointer;
  font-weight: 600;
}
.policy-block {
  margin-top: 16px;
}
.policy-block > small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 8px;
}
.policy-block .path-grid {
  margin-bottom: 0;
}
.path-card {
  text-align: left;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 12px 14px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  transition: background 0.1s ease, border-color 0.1s ease;
}
.path-card:hover {
  background: var(--gray2);
}
.path-card.is-active {
  background: var(--accent-wash);
  border-color: var(--accent-line);
}
.path-card small {
  display: block;
  color: var(--muted);
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
}
.path-card b {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 2px;
}
.chooser h3,
.resume-box h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.chooser {
  margin-bottom: 22px;
}
.resume-box {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 16px;
  background: var(--surface);
}
.resume-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.resume-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.resume-card {
  flex: 1;
  text-align: left;
  border: 1px solid var(--line);
  background: var(--gray3);
  border-radius: var(--radius);
  padding: 10px 12px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
}
.resume-card b {
  display: block;
  margin-bottom: 2px;
}
.flow-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  margin: 14px 0;
}
.slot-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
}
.slot-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
}
.slot-photo {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: var(--gray3);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.slot-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.family-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.family-chip {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 999px;
  padding: 4px 10px;
  font: inherit;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
}
.family-chip.is-active {
  background: var(--accent-wash);
  border-color: var(--accent-line);
}
.erp-more {
  margin-top: 22px;
  color: var(--muted);
  font-size: 13px;
}
.erp-more summary {
  cursor: pointer;
  margin-bottom: 12px;
}
.style-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.row-issues {
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 14px;
  background: var(--gray3);
}
.row-issues ul {
  margin: 8px 0 0;
  padding-left: 4px;
  list-style: none;
  color: var(--ink-2);
}
.row-issues li + li {
  margin-top: 4px;
}
.policy-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.policy-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
  padding: 12px 14px;
}
.policy-card.is-redline {
  background: var(--red-soft);
  border-color: var(--red-line);
}
.policy-card small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
}
.policy-card b {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
}
.policy-card ul {
  margin: 0;
  padding-left: 16px;
  color: var(--ink-2);
}
.policy-card li + li {
  margin-top: 4px;
}
.sheet-preview {
  margin-top: 16px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.sheet-preview table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.sheet-preview th,
.sheet-preview td {
  padding: 8px 10px;
  border-right: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
.sheet-preview th {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
}
.sheet-preview .need {
  margin-left: 6px;
  font-size: 10px;
  font-weight: 500;
  color: #ffcdce;
}
.sheet-preview tr.is-sample td {
  color: var(--muted);
  font-style: italic;
  background: var(--gray3);
}
.sheet-preview-full table {
  min-width: max-content;
}
.sheet-preview th.is-required-col {
  background: #7f1d1d;
}
@media (max-width: 900px) {
  .path-grid,
  .path-grid-2,
  .policy-grid {
    grid-template-columns: 1fr;
  }
}

.photobank-panel {
  margin-top: 12px;
}

.photobank-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.photobank-item {
  border: 2px solid transparent;
  border-radius: 10px;
  padding: 6px;
  background: var(--panel);
  cursor: pointer;
  text-align: left;
}

.photobank-item.is-selected {
  border-color: var(--accent);
}

.photobank-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  display: block;
}

.photobank-item span {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-next-box {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
}

.category-next-box ul {
  margin: 10px 0 8px;
  padding-left: 18px;
  color: var(--ink-2);
}

.category-next-box li + li {
  margin-top: 6px;
}

.doc-grid-toolbar {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}

.doc-grid-wrap {
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  max-height: 520px;
}

.doc-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.doc-grid th,
.doc-grid td {
  padding: 6px 8px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}

.doc-grid th {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}

.doc-grid .need {
  margin-left: 4px;
  font-size: 10px;
  font-weight: 500;
  color: #ffcdce;
}

.doc-grid td:first-child,
.doc-grid th:first-child {
  color: var(--muted);
  width: 36px;
  text-align: center;
}
</style>
