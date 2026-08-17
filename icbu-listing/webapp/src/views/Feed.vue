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
        <p class="muted">三条路最后都是：你出图、单价、起订量；没写的数系统不会编。</p>
        <div class="path-grid">
          <button class="path-card" @click="startPath('photo')">
            <small>默认走这条</small>
            <b>有实拍</b>
            <p class="muted">手机或工厂已经拍好了。上传图，再填单价和起订量。</p>
          </button>
          <button class="path-card" @click="startPath('ai')">
            <small>一张实拍都没有</small>
            <b>平台画图</b>
            <p class="muted">只写品名（最好再贴一张参考图），平台画 6 张后再填价。生成图会标黄，不是实拍。</p>
          </button>
          <button class="path-card" @click="startPath('excel')">
            <small>一次很多、每个价不一样</small>
            <b>填表批量</b>
            <p class="muted">下载短表，一行一个商品。有图用图（一张也行），没图的行按品名画一套并标黄。</p>
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
        <el-upload
          v-if="photoMode === 'single'"
          v-model:file-list="files"
          list-type="picture-card"
          :auto-upload="false"
          :limit="6"
          accept="image/*"
        >
          <span style="font-size: 22px">+</span>
        </el-upload>
        <el-upload
          v-else
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
          <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱</el-button>
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
          title="没写的数一律不画"
          description="尺寸、装箱量、颜色、认证、配件只按你填的来。空着的项不会编 200mm、24 支/箱、CE 这类数字或标志。商品上已经印好的字会保留。"
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
          <el-form-item label="参考图">
            <div>
              <el-input v-model="aiForm.referenceUrl" placeholder="可选。贴一张产品图网址，套图会按这张货长" />
              <p class="muted" style="margin: 6px 0 0">有产品图时务必贴上。比只写品名稳得多。</p>
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

    <!-- 表格批量 -->
    <template v-else>
      <FishboneSteps v-model="excelStep" :steps="excelSteps" :reached="excelReached" />

      <div v-if="excelStep === 0" class="step-panel">
        <h3>这批货是哪一类</h3>
        <p class="muted">一次上很多、每个价不一样时用这张短表。整表共用一个类目。选错后面属性全废，所以这一步要人点一下，不能交给 AI。</p>
        <div style="margin-top: 16px">
          <el-button @click="openCategory">{{ sheetPlan.category_name || "选择类目" }}</el-button>
          <p v-if="sheetPlan.ai_attrs?.length" class="muted" style="margin-top: 10px">
            选好后，标题、关键词和 {{ sheetPlan.ai_attrs.map((item) => item.header).join("、") }} 都由 AI 补。
          </p>
        </div>
        <div class="step-actions">
          <el-button type="primary" :disabled="!excel.categoryId" @click="advanceExcel(1)">下一步，下载表格</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 1" class="step-panel">
        <h3>下载填写表</h3>
        <p class="muted">
          这张表的列是平台定的短表（货号、单价、起订量、图片、品牌、品名、备注），不是阿里后台下载的 40 列。
          货号、单价、起订量必填；图片选填，一张也行，没图留空。上面选的官方类目只用来让 AI 按该叶子的发布规则补标题和属性。
        </p>
        <div class="sheet-preview" v-if="previewColumns.length">
          <table>
            <thead>
              <tr>
                <th v-for="col in previewColumns" :key="col.id">
                  {{ col.label }}<span v-if="col.required" class="need">必填</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr class="is-sample">
                <td v-for="col in previewColumns" :key="col.id">{{ col.example || "—" }}</td>
              </tr>
              <tr>
                <td v-for="col in previewColumns" :key="`${col.id}-empty`">
                  <span class="muted">{{ col.id === "sku" ? "从这行开始写你的货" : "" }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="muted" style="margin-top: 8px">灰色那行是示例，导入时自动跳过。一行一个商品，往下接着写。</p>
        </div>
        <div class="policy-grid" style="margin-top: 16px">
          <section class="policy-card">
            <small>你填</small>
            <b>就这几列</b>
            <ul>
              <li v-for="item in policy.user_fills" :key="item.id">
                {{ item.label }}<span v-if="!item.required" class="muted"> 选填</span>
              </li>
            </ul>
          </section>
          <section class="policy-card">
            <small>AI 填</small>
            <b>不要写进表</b>
            <ul>
              <li v-for="item in policy.ai_fills" :key="item.id">{{ item.label }}</li>
            </ul>
          </section>
          <section class="policy-card is-redline">
            <small>红线</small>
            <b>不准交给 AI</b>
            <ul>
              <li v-for="item in policy.redline" :key="item.id">
                <strong>{{ item.label }}</strong>
              </li>
            </ul>
          </section>
        </div>
        <div class="step-actions">
          <el-button @click="excelStep = 0">上一步</el-button>
          <el-button type="primary" @click="downloadAndAdvance">下载填写表</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 2" class="step-panel">
        <h3>填完传回来</h3>
        <p class="muted">灰色那行是示例，导入时会自动跳过。从下一行开始写你的货。</p>
        <el-upload
          v-model:file-list="excelFile"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xlsm,.xls"
          drag
          style="margin-top: 14px"
          @change="onExcelPicked"
        >
          <div style="padding: 22px 0">把填好的表格拖到这里</div>
        </el-upload>
        <el-alert
          v-for="warning in excel.preview?.warnings || []"
          :key="warning"
          type="warning"
          :title="warning"
          :closable="false"
          style="margin: 12px 0 0"
        />
        <div v-if="excel.preview?.row_issues?.length" class="row-issues">
          <b>成稿前先看这几行</b>
          <p class="muted">红的要改完再传。黄的只是提醒。</p>
          <ul>
            <li v-for="(issue, index) in excel.preview.row_issues.slice(0, 12)" :key="index">
              <span :class="['dot', issue.level]"></span>
              第 {{ issue.line }} 行 {{ issue.sku }}：{{ issue.message }}
            </li>
          </ul>
        </div>
        <p v-if="excel.preview" class="muted" style="margin-top: 12px">
          识别到 {{ excel.preview.row_count }} 个商品，其中 {{ excel.preview.ready_count }} 个价和起订量齐了。
          <template v-if="excel.preview.image_stats">
            表里有图 {{ excel.preview.image_stats.with_sheet_images }} 个
            <template v-if="excel.preview.image_stats.single_sheet_image">
              （{{ excel.preview.image_stats.single_sheet_image }} 个只有一张）
            </template>
            ，没图 {{ excel.preview.image_stats.without_sheet_images }} 个。
          </template>
        </p>
        <div class="step-actions">
          <el-button @click="excelStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!excelFile.length" @click="advanceExcel(3)">下一步，图怎么处理</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 3" class="step-panel">
        <h3>这批图怎么处理</h3>
        <p class="muted">有图、没图、只有一张，都可以在同一张表里。先选这批怎么走，再决定要不要拖本地图。</p>
        <div class="path-grid" style="margin-top: 14px">
          <button
            type="button"
            class="path-card"
            :class="{ 'is-active': excel.imageMode === 'mixed' }"
            @click="excel.imageMode = 'mixed'"
          >
            <small>推荐</small>
            <b>有图用图，没图画套图</b>
            <p class="muted">表里或拖进来的图当实拍，一张也行。没对上图的行按品名画 6 张，并标黄不是实拍。</p>
          </button>
          <button
            type="button"
            class="path-card"
            :class="{ 'is-active': excel.imageMode === 'generate_all' }"
            @click="excel.imageMode = 'generate_all'"
          >
            <small>这批都没实拍</small>
            <b>全部按品名画套图</b>
            <p class="muted">不管表里有没有链接，都画 6 张。生成图会标黄，不准冒充实拍。</p>
          </button>
          <button
            type="button"
            class="path-card"
            :class="{ 'is-active': excel.imageMode === 'photos_only' }"
            @click="excel.imageMode = 'photos_only'"
          >
            <small>只要实拍</small>
            <b>只做成有图的行</b>
            <p class="muted">没对上图的行跳过。一张实拍也够，不会再补生成图。</p>
          </button>
        </div>
        <el-alert
          v-if="excel.imageMode !== 'photos_only'"
          type="warning"
          show-icon
          :closable="false"
          title="生成图不是实拍"
          description="没写的尺寸、装箱量、认证一律不画。没图的行出图要时间，额度不够会停在那一行。"
          style="margin-top: 14px"
        />
        <p class="muted" style="margin-top: 16px">
          {{ excelImageUploadHint }}
        </p>
        <el-upload
          v-if="excel.imageMode !== 'generate_all'"
          v-model:file-list="excelImages"
          :auto-upload="false"
          multiple
          accept="image/*"
          drag
          style="margin-top: 10px"
        >
          <div style="padding: 22px 0">把本地图拖进来，按货号命名，例如 SKU-1001.jpg 或 SKU-1001_1.jpg</div>
        </el-upload>
        <div class="step-actions">
          <el-button @click="excelStep = 2">上一步</el-button>
          <el-button type="primary" @click="advanceExcel(4)">下一步，开始成稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>开始成稿</h3>
        <p class="muted">{{ excelGoHint }} 关掉页面也不影响，去草稿箱只审红黄项即可。</p>
        <div class="step-actions">
          <el-button @click="excelStep = 3">上一步</el-button>
          <el-button
            type="primary"
            :loading="excel.loading"
            :disabled="!excelFile.length || !store.shopId || !excel.categoryId"
            @click="importSimple"
          >
            批量成稿
          </el-button>
        </div>
        <div v-if="excel.batch" style="margin-top: 18px">
          <p>共 {{ excel.batch.count }} 个商品，已成稿 {{ excelProgress.done }} 个。</p>
          <el-progress :percentage="excelPercent" :stroke-width="10" />
          <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱审红黄项</el-button>
        </div>
      </div>

      <details class="erp-more">
        <summary>已有领星 / 店小秘 / 马帮的现成表</summary>
        <el-radio-group v-model="excel.style" class="style-grid" @change="onStyleChange">
          <el-radio-button v-for="item in otherStyles" :key="item.id" :value="item.id">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <p class="muted" style="margin: 12px 0 16px">{{ currentStyle?.summary }}</p>
        <el-form label-width="88px" style="max-width: 640px">
          <el-form-item v-if="currentStyle?.needs_listing_template" label="刊登模板">
            <el-select v-model="excel.listingTemplateId" placeholder="先选一个类目模板" style="width: 320px">
              <el-option
                v-for="item in listingTemplates"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="模板">
            <el-button @click="downloadTemplate">下载 {{ currentStyle?.label || "" }} 模板</el-button>
          </el-form-item>
          <el-form-item label="填好的表">
            <el-upload v-model:file-list="excelFile" :auto-upload="false" :limit="1" accept=".xlsx,.xlsm,.xls">
              <el-button>选择表格</el-button>
            </el-upload>
          </el-form-item>
          <el-form-item label="配套图片">
            <el-upload v-model:file-list="excelImages" :auto-upload="false" multiple accept="image/*">
              <el-button>选择图片</el-button>
            </el-upload>
          </el-form-item>
          <el-button :loading="excel.loading" :disabled="!excelFile.length" @click="previewExcel">探测表头</el-button>
          <el-button type="primary" :loading="excel.loading" :disabled="!excel.preview" @click="importExcel">
            确认导入
          </el-button>
        </el-form>
        <el-table v-if="excel.style !== 'simple' && excel.preview" :data="mappingRows" size="small" style="max-width: 640px; margin-top: 12px">
          <el-table-column prop="header" label="表格列" />
          <el-table-column label="对到">
            <template #default="{ row }">
              <el-select v-model="excel.mapping[row.header]" clearable placeholder="忽略这一列">
                <el-option v-for="field in excel.preview.fields" :key="field.id" :label="field.label" :value="field.id" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </details>
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
const photoStep = ref(0);
const photoReached = ref(0);
const aiStep = ref(0);
const aiReached = ref(0);
const excelStep = ref(0);
const excelReached = ref(0);

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
const excelSteps = [
  { key: "cat", label: "选类目" },
  { key: "dl", label: "下载表格" },
  { key: "up", label: "传回表格" },
  { key: "img", label: "图怎么处理" },
  { key: "go", label: "开始成稿" },
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
  planning: false,
  categoryId: "",
  categoryName: "",
});
const categoryTarget = ref("excel");
const loading = ref(false);
const files = ref([]);
const batchFiles = ref([]);
const batch = ref(null);
const progress = ref({ done: 0 });
const form = reactive({ sku: "", price: "", moq: "", note: "" });
const styles = ref([]);
const listingTemplates = ref([]);
const excelFile = ref([]);
const excelImages = ref([]);
const excel = reactive({
  style: route.query.style || "simple",
  listingTemplateId: "",
  categoryId: route.query.category || "",
  createDrafts: true,
  loading: false,
  preview: null,
  mapping: {},
  batch: null,
  imageMode: "mixed",
});
const sheetPlan = ref({ user_fills: [], ai_fills: [], redline: [], ai_attrs: [], category_name: "", preview: null });
const categoryBrowser = ref(false);
const excelProgress = ref({ done: 0 });
let timer = null;
let excelTimer = null;
let imageTimer = null;

const currentStyle = computed(() => styles.value.find((item) => item.id === excel.style));
const otherStyles = computed(() => styles.value.filter((item) => item.id !== "simple"));
const policy = computed(() => ({
  user_fills: sheetPlan.value.user_fills?.length ? sheetPlan.value.user_fills : currentStyle.value?.policy?.user_fills || [],
  ai_fills: sheetPlan.value.ai_fills?.length ? sheetPlan.value.ai_fills : currentStyle.value?.policy?.ai_fills || [],
  redline: sheetPlan.value.redline?.length ? sheetPlan.value.redline : currentStyle.value?.policy?.redline || [],
}));
const previewColumns = computed(() => sheetPlan.value.preview?.columns || policy.value.user_fills.map((item) => ({
  id: item.id,
  label: item.label,
  required: item.required,
  example: "",
})));
const mappingRows = computed(() => (excel.preview?.headers || []).map((header) => ({ header })));
const excelPercent = computed(() => {
  if (!excel.batch?.count) return 0;
  return Math.min(100, Math.round((excelProgress.value.done / excel.batch.count) * 100));
});
const excelImageUploadHint = computed(() => {
  if (excel.imageMode === "photos_only") {
    return "有本地图就拖进来，按货号命名。一张也行。对不上的行会跳过。";
  }
  if (excel.imageMode === "generate_all") {
    return "不用传图。有参考图链接可以写在表里，只当画图参考，不当实拍。";
  }
  return "有本地图就拖进来，按货号命名，一张也行。没有的行按品名画套图。表里写了链接也不用再传。";
});
const excelGoHint = computed(() => {
  if (excel.imageMode === "generate_all") {
    return "这批都会画套图并标黄。后台一条一条过。";
  }
  if (excel.imageMode === "photos_only") {
    return "只做成对上图的行，一张也行。没图的跳过。";
  }
  return "有图的用实拍（一张也行），没图的按品名画套图并标黄。后台一条一条过。";
});
const percent = computed(() => {
  if (!batch.value?.count) return 0;
  return Math.min(100, Math.round((progress.value.done / batch.value.count) * 100));
});
const hasPhotos = computed(() => (photoMode.value === "single" ? files.value.length : batchFiles.value.length));
const imagePercent = computed(() => {
  const total = imageJob.value?.total || 6;
  return Math.min(100, Math.round(((imageJob.value?.done || 0) / total) * 100));
});

function pathToTab(path) {
  if (path === "ai") return "ai";
  if (path === "excel") return "excel";
  return "single";
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
      style: excel.style,
      listingTemplateId: excel.listingTemplateId,
      categoryId: excel.categoryId,
      mapping: excel.mapping,
      preview: excel.preview,
      batch: excel.batch,
      imageMode: excel.imageMode,
    },
    categoryName: sheetPlan.value.category_name || "",
    rowCount: excel.preview?.row_count || excel.batch?.count || batch.value?.count || 0,
    imageJobId: imageJob.value?.id || "",
    batchId: batch.value?.batch_id || excel.batch?.batch_id || "",
  };
}

function currentStep() {
  if (tab.value === "ai") return aiStep.value;
  if (tab.value === "excel") return excelStep.value;
  return photoStep.value;
}

function currentReached() {
  if (tab.value === "ai") return aiReached.value;
  if (tab.value === "excel") return excelReached.value;
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
  if (!sessionId.value || restoring.value) return;
  const raws = (list || []).filter((item) => item.raw);
  const keep = (list || []).filter((item) => !item.raw && item.name).map((item) => item.name);
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
    planning: false,
  });
  if (payload.excel) {
    excel.style = payload.excel.style || excel.style;
    excel.listingTemplateId = payload.excel.listingTemplateId || "";
    excel.categoryId = payload.excel.categoryId || "";
    excel.mapping = payload.excel.mapping || {};
    excel.preview = payload.excel.preview || null;
    excel.batch = payload.excel.batch || null;
    excel.imageMode = payload.excel.imageMode || excel.imageMode || "mixed";
  }
  files.value = filesFromSession(session, "photos");
  batchFiles.value = filesFromSession(session, "batch");
  excelFile.value = filesFromSession(session, "excel");
  excelImages.value = filesFromSession(session, "excel_images");
  imageJob.value = payload.imageJobId ? { id: payload.imageJobId, status: "queued", slots: [] } : null;
  batch.value = payload.batchId && tab.value === "single" ? { batch_id: payload.batchId, count: payload.rowCount || 0 } : null;
  if (tab.value === "ai") {
    aiStep.value = session.step || 0;
    aiReached.value = session.reached || 0;
  } else if (tab.value === "excel") {
    excelStep.value = session.step || 0;
    excelReached.value = session.reached || 0;
  } else {
    photoStep.value = session.step || 0;
    photoReached.value = session.reached || 0;
  }
  restoring.value = false;
}

async function startPath(path) {
  try {
    const created = await api.createFeedSession({ path, shop_id: store.shopId || "" });
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
    if (excel.batch?.batch_id) {
      clearInterval(excelTimer);
      excelTimer = setInterval(pollExcel, 3000);
      await pollExcel();
    }
    if (excel.categoryId) await loadSheetPlan();
  } catch (error) {
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

function advanceExcel(index) {
  excelReached.value = Math.max(excelReached.value, index);
  excelStep.value = index;
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
  try {
    styles.value = await api.excelStyles();
    listingTemplates.value = store.shopId ? await api.templates({ shop_id: store.shopId }) : [];
    onStyleChange();
    await loadSheetPlan();
    if (excel.categoryId) excelReached.value = Math.max(excelReached.value, 1);
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
watch(excelFile, () => syncKind("excel", excelFile.value), { deep: true });
watch(excelImages, () => syncKind("excel_images", excelImages.value), { deep: true });
watch(
  () => excel.imageMode,
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 400);
  },
);

async function startGenerate() {
  if (!aiForm.productName && !aiForm.note && !aiForm.familyId) {
    ElMessage.warning("先写品名，或选一个类目");
    return;
  }
  aiForm.planning = true;
  try {
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
      reference_urls: aiForm.referenceUrl.trim() ? [aiForm.referenceUrl.trim()] : [],
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

function onStyleChange() {
  excel.createDrafts = Boolean(currentStyle.value?.create_drafts_default);
  excel.preview = null;
}

async function onExcelPicked() {
  if (excel.style === "simple" && excelFile.value[0]?.raw) {
    await previewExcel();
  }
}

async function importSimple() {
  excel.createDrafts = true;
  if (!excel.preview && excelFile.value[0]?.raw) await previewExcel();
  if (excel.preview || sessionId.value) await importExcel();
}

async function loadSheetPlan() {
  sheetPlan.value = await api.excelSheetPlan({
    shop_id: store.shopId || "",
    category_id: excel.categoryId || "",
  });
}

function openCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryTarget.value = "excel";
  categoryBrowser.value = true;
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
  if (categoryTarget.value === "ai") {
    aiForm.categoryId = node.category_id;
    aiForm.categoryName = node.label || node.name || node.cn_name || "";
    try {
      const planned = await api.planImages({
        product_name: aiForm.productName,
        category_hint: aiForm.categoryName,
        note: aiForm.note,
      });
      aiForm.familyId = planned.family?.id || "";
      ElMessage.success(`已选「${aiForm.categoryName}」，出图按「${planned.family?.name || "通用"}」`);
    } catch {
      ElMessage.success(`已选「${aiForm.categoryName}」`);
    }
    return;
  }
  excel.categoryId = node.category_id;
  try {
    await loadSheetPlan();
    ElMessage.success(`已选「${sheetPlan.value.category_name || node.label}」`);
    advanceExcel(1);
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function downloadTemplate() {
  window.location.href = api.excelTemplateUrl(excel.style, excel.listingTemplateId, {
    categoryId: excel.categoryId,
    shopId: store.shopId,
  });
}

function downloadAndAdvance() {
  downloadTemplate();
  advanceExcel(2);
}

async function previewExcel() {
  if (!excelFile.value[0]?.raw) {
    ElMessage.warning("先选一个表格");
    return;
  }
  const body = new FormData();
  body.append("style", excel.style);
  body.append("shop_id", store.shopId || "");
  body.append("category_id", excel.categoryId || "");
  body.append("image_mode", excel.imageMode || "mixed");
  body.append("file", excelFile.value[0].raw);
  excel.loading = true;
  try {
    excel.preview = await api.excelPreview(body);
    excel.mapping = { ...(excel.preview.mapping || {}) };
    await persistSession();
    ElMessage.success(`识别到 ${excel.preview.row_count} 个商品`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    excel.loading = false;
  }
}

async function importExcel() {
  if (!excelFile.value[0]?.raw && !sessionId.value) return;
  const body = new FormData();
  body.append("style", excel.style);
  body.append("shop_id", store.shopId || "");
  body.append("mapping", JSON.stringify(excel.mapping));
  body.append("create_drafts", excel.createDrafts ? "true" : "false");
  body.append("listing_template_id", excel.listingTemplateId);
  body.append("category_id", excel.categoryId);
  body.append("session_id", sessionId.value);
  body.append("image_mode", excel.imageMode || "mixed");
  if (excelFile.value[0]?.raw) body.append("file", excelFile.value[0].raw);
  excelImages.value.forEach((item) => item.raw && body.append("images", item.raw));
  excel.loading = true;
  try {
    excel.batch = await api.excelImport(body);
    excelProgress.value = { done: 0 };
    sessionId.value = "";
    clearInterval(excelTimer);
    excelTimer = setInterval(pollExcel, 3000);
    ElMessage.success(`已接收 ${excel.batch.count} 个商品，后台在成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    excel.loading = false;
  }
}

async function pollExcel() {
  if (!excel.batch) return;
  try {
    excelProgress.value = await api.batchProgress(excel.batch.batch_id);
    if (excelProgress.value.done >= excel.batch.count) clearInterval(excelTimer);
  } catch {
    clearInterval(excelTimer);
  }
}

onUnmounted(() => {
  clearInterval(timer);
  clearInterval(excelTimer);
  clearInterval(imageTimer);
});

async function submitOne() {
  if (!files.value.length) {
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
  files.value.forEach((item) => item.raw && body.append("files", item.raw));
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
@media (max-width: 900px) {
  .path-grid,
  .policy-grid {
    grid-template-columns: 1fr;
  }
}
</style>
